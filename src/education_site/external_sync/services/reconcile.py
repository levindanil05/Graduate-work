from __future__ import annotations

import os
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from django.db.models import Q
from django.utils import timezone

from documents.entities import VersionStatus
from documents.factory import build_document_service
from documents.models import DocumentVersion
from external_sync.models import (
    ExternalConnection,
    ExternalReplica,
    ExternalSyncSettings,
    OnActiveMissing,
    OutboundIntent,
    OutboundKind,
    OutboundStatus,
    RemoteObjectSnapshot,
    RemoteRole,
    ReplicaSyncState,
    SyncConflict,
    SyncRun,
    SyncRunStatus,
    WriteMode,
)
from external_sync.ports import ExternalStorageProvider, ReadOnlyStorageError
from external_sync.registry import ConnectionRegistry
from plans.archive_naming import choose_archive_filename
from plans.placement_policy import (
    archive_directory_for_active,
    build_active_path_from_metadata,
    classify_path,
    primary_active_path,
)


class ReconciliationService:
    def __init__(
        self,
        connection: ExternalConnection,
        provider: ExternalStorageProvider | None = None,
    ) -> None:
        self.connection = connection
        self.provider = provider or ConnectionRegistry().build_provider(connection)
        self.documents = build_document_service()
        self.report: list[str] = []

    def _gate_pull(self) -> bool:
        settings = ExternalSyncSettings.get_solo()
        if not settings.external_sync_enabled or not self.connection.enabled:
            self.report.append('Получение изменений выключено глобально или для подключения.')
            return False
        if not self.connection.pull_enabled:
            self.report.append('Получение изменений выключено для этого подключения.')
            return False
        return True

    def _gate_push(self) -> bool:
        settings = ExternalSyncSettings.get_solo()
        if not settings.external_sync_enabled or not self.connection.enabled:
            return False
        if self.connection.is_read_only_mode():
            return False
        return self.connection.push_enabled

    def _acquire_lease(self) -> bool:
        now = timezone.now()
        token = uuid.uuid4().hex
        updated = ExternalConnection.objects.filter(pk=self.connection.pk).filter(
            Q(lease_until__isnull=True) | Q(lease_until__lt=now),
        ).update(lease_token=token, lease_until=now + timedelta(hours=1))
        if not updated:
            return False
        self.connection.refresh_from_db()
        return self.connection.lease_token == token

    def _release_lease(self) -> None:
        ExternalConnection.objects.filter(pk=self.connection.pk).update(
            lease_token='',
            lease_until=None,
        )

    def run(
        self,
        *,
        pull_only: bool = False,
        push_only: bool = False,
        sync_run: SyncRun | None = None,
    ) -> SyncRun:
        if sync_run is None:
            sync_run = SyncRun.objects.create(
                connection=self.connection,
                status=SyncRunStatus.PLANNING,
                idempotency_key=uuid.uuid4().hex,
            )
        else:
            sync_run.status = SyncRunStatus.PLANNING
            sync_run.save(update_fields=['status', 'updated_at'])

        if not self.connection.manual_run_enabled and not self.connection.schedule_enabled:
            sync_run.status = SyncRunStatus.PAUSED
            sync_run.stop_reason = 'Ручной запуск запрещён настройкой подключения'
            sync_run.finished_at = timezone.now()
            sync_run.save()
            return sync_run

        if not self._acquire_lease():
            sync_run.status = SyncRunStatus.PAUSED
            sync_run.stop_reason = 'Другой прогон уже выполняется для этого подключения'
            sync_run.finished_at = timezone.now()
            sync_run.save()
            return sync_run

        try:
            sync_run.status = SyncRunStatus.APPLYING
            sync_run.save(update_fields=['status', 'updated_at'])

            do_push = self._gate_push() and not pull_only
            do_pull = self._gate_pull() and not push_only

            if do_push:
                self._process_outbound_intents(sync_run)
            if do_pull:
                self._process_pull(sync_run)

            if not do_push and not do_pull:
                sync_run.status = SyncRunStatus.PAUSED
                sync_run.stop_reason = 'Нет разрешённых направлений синхронизации'
            else:
                sync_run.status = SyncRunStatus.COMPLETED
                self.connection.last_checkpoint_at = timezone.now()
                self.connection.save(update_fields=['last_checkpoint_at', 'updated_at'])
        except Exception as exc:  # noqa: BLE001
            sync_run.status = SyncRunStatus.FAILED
            sync_run.stop_reason = str(exc)
            sync_run.errors_count += 1
            self.report.append(f'Ошибка прогона: {exc}')
        finally:
            self._release_lease()
            sync_run.report_lines = self.report
            sync_run.finished_at = timezone.now()
            sync_run.save()

        return sync_run

    def _process_outbound_intents(self, sync_run: SyncRun) -> None:
        intents = OutboundIntent.objects.filter(
            connection=self.connection,
            status__in=[OutboundStatus.PENDING, OutboundStatus.PAUSED_BY_SWITCH],
        ).select_related('version', 'version__document')

        for intent in intents:
            if not self._gate_push():
                intent.status = OutboundStatus.PAUSED_BY_SWITCH
                intent.save(update_fields=['status', 'updated_at'])
                continue
            intent.status = OutboundStatus.IN_PROGRESS
            intent.save(update_fields=['status', 'updated_at'])
            try:
                if intent.kind == OutboundKind.PUBLISH_ACTIVE:
                    self._publish_active(intent)
                    sync_run.published_count += 1
                elif intent.kind == OutboundKind.MOVE_TO_ARCHIVE:
                    self._move_to_archive(intent)
                    sync_run.archived_count += 1
                intent.status = OutboundStatus.DONE
                intent.save(update_fields=['status', 'updated_at'])
            except ReadOnlyStorageError as exc:
                intent.status = OutboundStatus.PAUSED_BY_SWITCH
                intent.error_message = str(exc)
                intent.save(update_fields=['status', 'error_message', 'updated_at'])
            except Exception as exc:  # noqa: BLE001
                intent.status = OutboundStatus.FAILED
                intent.error_message = str(exc)
                intent.save(update_fields=['status', 'error_message', 'updated_at'])
                sync_run.errors_count += 1
                self.report.append(f'Ошибка намерения {intent.id}: {exc}')

    def _publish_active(self, intent: OutboundIntent) -> None:
        version = intent.version
        active_path = intent.desired_remote_path or build_active_path_from_metadata(
            version.extracted_metadata or {},
            version.source_filename,
        )
        storage = self.documents.storage
        local = storage.resolve_path(version.storage_key)
        self.provider.upload(str(local), active_path, overwrite=True)
        self._upsert_replica(version, active_path, RemoteRole.ACTIVE, ReplicaSyncState.IN_SYNC)
        intent.desired_remote_path = active_path
        intent.save(update_fields=['desired_remote_path', 'updated_at'])

    def _move_to_archive(self, intent: OutboundIntent) -> None:
        version = intent.version
        replica = (
            ExternalReplica.objects.filter(
                connection=self.connection,
                version=version,
                role=RemoteRole.ACTIVE,
            )
            .order_by('-is_primary', '-last_reconciled_at')
            .first()
        )
        active_path = replica.remote_path if replica else intent.desired_remote_path
        if not active_path:
            active_path = build_active_path_from_metadata(
                version.extracted_metadata or {},
                version.source_filename,
            )
        archive_dir = archive_directory_for_active(active_path)
        archive_name = choose_archive_filename(
            Path(active_path).name,
            version.created_at,
            occupied_names=set(),
        )
        archive_path = f'{archive_dir}/{archive_name}'.replace('//', '/')
        try:
            self.provider.move(active_path, archive_path, overwrite=False)
        except FileNotFoundError:
            pass
        self._upsert_replica(version, archive_path, RemoteRole.ARCHIVE, ReplicaSyncState.IN_SYNC)
        if replica:
            replica.sync_state = ReplicaSyncState.IN_SYNC
            replica.role = RemoteRole.ARCHIVE
            replica.remote_path = archive_path
            replica.last_reconciled_at = timezone.now()
            replica.save()

    def _process_pull(self, sync_run: SyncRun) -> None:
        inventory = [item for item in self.provider.list('/') if not item.is_dir]
        seen_paths: set[str] = set()

        for item in inventory:
            role = classify_path(item.path)
            if role == RemoteRole.IGNORED:
                sync_run.skipped_count += 1
                continue
            seen_paths.add(item.path)
            snapshot = RemoteObjectSnapshot.objects.filter(
                connection=self.connection,
                remote_path=item.path,
            ).first()

            fingerprint_same = (
                snapshot
                and snapshot.md5
                and item.md5
                and snapshot.md5 == item.md5
                and snapshot.size == item.size
            )
            if fingerprint_same and snapshot.content_hash:
                sync_run.skipped_count += 1
                self._touch_snapshot(snapshot, item)
                continue

            trusted_status = (
                VersionStatus.APPROVED if role == RemoteRole.ACTIVE else VersionStatus.ARCHIVED
            )
            try:
                version = self._import_remote_file(item, trusted_status, sync_run)
            except Exception as exc:  # noqa: BLE001
                sync_run.errors_count += 1
                self.report.append(f'Ошибка импорта {item.path}: {exc}')
                continue

            if version is None:
                continue

            self._upsert_snapshot(item, role, version)
            self._upsert_replica(
                version,
                item.path,
                role,
                ReplicaSyncState.IN_SYNC,
                is_primary=(role == RemoteRole.ACTIVE),
            )
            sync_run.imported_count += 1

        self._handle_missing_remotes(seen_paths, sync_run)

    def _import_remote_file(self, item, trusted_status, sync_run):
        with tempfile.NamedTemporaryFile(suffix='.plx', delete=False) as tmp:
            tmp_path = tmp.name
        try:
            self.provider.download(item.path, tmp_path)
            result = self.documents.import_trusted_plx(
                file_path=Path(tmp_path),
                source_filename=Path(item.path).name,
                trusted_status=trusted_status,
            )
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        if result.status == 'already_exists':
            sync_run.duplicates_count += 1
            if result.version_id:
                return DocumentVersion.objects.get(pk=result.version_id)
            return None
        if result.status == 'ambiguous_match':
            sync_run.skipped_count += 1
            self.report.append(f'Требует обработки: неоднозначное совпадение для {item.path}')
            return None
        if result.version_id:
            return DocumentVersion.objects.get(pk=result.version_id)
        return None

    def _upsert_snapshot(self, item, role, version: DocumentVersion) -> None:
        RemoteObjectSnapshot.objects.update_or_create(
            connection=self.connection,
            remote_path=item.path,
            defaults={
                'remote_id': item.remote_id or '',
                'role': role,
                'size': item.size,
                'md5': item.md5 or '',
                'modified_at': item.modified_at,
                'content_hash': version.content_hash,
                'version': version,
            },
        )

    def _touch_snapshot(self, snapshot: RemoteObjectSnapshot, item) -> None:
        snapshot.modified_at = item.modified_at
        snapshot.size = item.size
        snapshot.md5 = item.md5 or snapshot.md5
        snapshot.save(update_fields=['modified_at', 'size', 'md5', 'updated_at'])

    def _upsert_replica(
        self,
        version: DocumentVersion,
        remote_path: str,
        role: str,
        sync_state: str,
        *,
        is_primary: bool = False,
    ) -> None:
        if is_primary:
            ExternalReplica.objects.filter(
                connection=self.connection,
                version__document_id=version.document_id,
                role=RemoteRole.ACTIVE,
            ).update(is_primary=False)
        ExternalReplica.objects.update_or_create(
            connection=self.connection,
            remote_path=remote_path,
            defaults={
                'version': version,
                'role': role,
                'is_primary': is_primary,
                'sync_state': sync_state,
                'last_reconciled_at': timezone.now(),
            },
        )

    def _handle_missing_remotes(self, seen_paths: set[str], sync_run: SyncRun) -> None:
        snapshots = RemoteObjectSnapshot.objects.filter(
            connection=self.connection,
            role=RemoteRole.ACTIVE,
        ).exclude(remote_path__in=seen_paths)

        for snapshot in snapshots.select_related('version', 'version__document'):
            if self.connection.on_active_missing == OnActiveMissing.ARCHIVE_LOCAL:
                version = snapshot.version
                if version and version.status == VersionStatus.APPROVED.value:
                    domain_version = self.documents.versions.get(version.id)
                    if domain_version:
                        self.documents._archive_approved_version(
                            domain_version,
                            actor_user_id=0,
                            action_comment='Файл исчез на внешнем хранилище',
                        )
            else:
                SyncConflict.objects.create(
                    connection=self.connection,
                    version=snapshot.version,
                    remote_path=snapshot.remote_path,
                    summary=f'Актуальный файл отсутствует на диске: {snapshot.remote_path}',
                )
                if snapshot.version_id:
                    ExternalReplica.objects.filter(
                        connection=self.connection,
                        version_id=snapshot.version_id,
                        remote_path=snapshot.remote_path,
                    ).update(sync_state=ReplicaSyncState.MISSING_REMOTE)
                sync_run.conflicts_count += 1
