from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from django.db import transaction
from django.utils.translation import gettext as _

from .contracts import (
    DiscussionRepository,
    DocumentNamingStrategy,
    DocumentRepository,
    HashingService,
    MetadataExtractor,
    PermissionService,
    StoragePort,
    VersionRepository,
    WorkflowRepository,
)
from .entities import (
    DiscussionMessage,
    Document,
    DocumentIdentity,
    DocumentType,
    DocumentVersion,
    VersionStatus,
    WorkflowAction,
    WorkflowTransition,
)
from .workflow_rules import get_rule

SYNC_ACTOR_USER_ID = 0


NAME_POLICY_KEEP_PLAN = 'keep_plan'
NAME_POLICY_USE_UPLOAD = 'use_upload'
NAME_POLICY_FROM_METADATA = 'from_metadata'
NAME_POLICIES = frozenset(
    {
        NAME_POLICY_KEEP_PLAN,
        NAME_POLICY_USE_UPLOAD,
        NAME_POLICY_FROM_METADATA,
    }
)


@dataclass
class UploadRequest:
    user_id: int
    document_type: DocumentType
    file_path: Path
    source_filename: str
    # Comment about uploaded changes (not discussion message).
    change_comment: str = ""
    # Пользователь подтвердил привязку к документу — имя файла может отличаться.
    skip_filename_check: bool = False
    # Добавить исходное/каноническое имя в алиасы после успешной загрузки версии.
    link_source_as_alias: bool = False
    # При привязке к существующему плану: keep_plan | use_upload | from_metadata.
    name_policy: str = NAME_POLICY_KEEP_PLAN


@dataclass
class UploadResult:
    document_id: UUID
    version_id: UUID | None
    status: str
    message: str


class DomainValidationError(ValueError):
    """Raised when business rule is violated."""


class DocumentApplicationService:
    """Use-case layer with domain rules and repository contracts.

    The service intentionally stays infrastructure-agnostic:
    storage, hash, metadata extraction and persistence are injected.
    """

    def __init__(
        self,
        *,
        documents: DocumentRepository,
        versions: VersionRepository,
        workflow: WorkflowRepository,
        discussions: DiscussionRepository,
        storage: StoragePort,
        hashing: HashingService,
        metadata_extractors: list[MetadataExtractor],
        naming_strategies: list[DocumentNamingStrategy],
        permissions: PermissionService,
    ) -> None:
        self.documents = documents
        self.versions = versions
        self.workflow = workflow
        self.discussions = discussions
        self.storage = storage
        self.hashing = hashing
        self.metadata_extractors = metadata_extractors
        self.naming_strategies = naming_strategies
        self.permissions = permissions

    def _resolve_naming_strategy(self, document_type: DocumentType) -> DocumentNamingStrategy:
        for strategy in self.naming_strategies:
            if strategy.supports(document_type):
                return strategy
        raise DomainValidationError(
            _('No naming strategy for document type: %(type)s') % {'type': document_type.value}
        )

    def _resolve_metadata_extractor(self, document_type: DocumentType) -> MetadataExtractor | None:
        for extractor in self.metadata_extractors:
            if extractor.supports(document_type):
                return extractor
        return None

    def suggest_document_matches(self, request: UploadRequest):
        """Кандидаты для подтверждения пользователем (PLX — по имени и метаданным)."""
        from .plx_identity import MatchContext, MatchSuggestion, find_plx_suggestions

        candidates = self.documents.list_for_type(request.document_type)
        incoming_meta: dict = {}

        if request.document_type == DocumentType.PLX:
            extractor = self._resolve_metadata_extractor(request.document_type)
            if extractor is not None:
                try:
                    incoming_meta = extractor.extract(request.file_path)
                except Exception:  # noqa: BLE001
                    incoming_meta = {}

            versions_by_doc = {
                doc.id: self.versions.get_active_version(doc.id) for doc in candidates
            }
            suggestions = find_plx_suggestions(
                source_filename=request.source_filename,
                incoming_meta=incoming_meta,
                documents=candidates,
                versions_by_doc=versions_by_doc,
            )
            return MatchContext(suggestions=suggestions, incoming_metadata=incoming_meta)

        strategy = self._resolve_naming_strategy(request.document_type)
        match = strategy.find_match(request.source_filename, candidates)
        suggestions: list[MatchSuggestion] = []
        if match.matched_document_id is not None:
            matched = self.documents.get(match.matched_document_id)
            if matched:
                suggestions.append(
                    MatchSuggestion(
                        document_id=matched.id,
                        canonical_name=matched.identity.canonical_name,
                        score=match.confidence,
                        reason='filename_exact',
                        aliases=matched.identity.aliases,
                    )
                )
            return MatchContext(suggestions=suggestions, incoming_metadata={})
        for doc_id in match.closest_document_ids:
            doc = self.documents.get(doc_id)
            if not doc:
                continue
            suggestions.append(
                MatchSuggestion(
                    document_id=doc.id,
                    canonical_name=doc.identity.canonical_name,
                    score=0.5,
                    reason='metadata_approx',
                    aliases=doc.identity.aliases,
                )
            )
        return MatchContext(suggestions=suggestions, incoming_metadata={})

    def try_match_existing_document(self, request: UploadRequest) -> list[Document]:
        """Resolve candidates to confirm user intent before linking chain."""
        suggestions = self.suggest_document_matches(request).suggestions
        result: list[Document] = []
        for suggestion in suggestions:
            doc = self.documents.get(suggestion.document_id)
            if doc is not None:
                result.append(doc)
        return result

    def _merge_identity_aliases(self, document: Document, *names: str) -> Document:
        aliases = set(document.identity.aliases)
        for name in names:
            cleaned = (name or '').strip()
            if cleaned:
                aliases.add(cleaned)
                aliases.add(Path(cleaned).name)
        document.identity = DocumentIdentity(
            canonical_name=document.identity.canonical_name,
            aliases=tuple(sorted(aliases)),
        )
        document.updated_at = datetime.now()
        return self.documents.save(document)

    def upload_new_document(self, request: UploadRequest) -> UploadResult:
        """Create new document when no matching chain is confirmed."""
        strategy = self._resolve_naming_strategy(request.document_type)
        canonical_name = strategy.canonicalize(request.source_filename)
        aliases = set(strategy.build_aliases(request.source_filename))

        extractor = self._resolve_metadata_extractor(request.document_type)
        if extractor is not None:
            try:
                metadata = extractor.extract(request.file_path)
            except Exception:  # noqa: BLE001
                metadata = {}
            canon_from_meta = (metadata or {}).get('canonical_filename')
            if isinstance(canon_from_meta, str) and canon_from_meta.strip():
                canonical_name = canon_from_meta.strip()
                aliases.add(canonical_name)
                aliases.add(Path(canonical_name).name)

        document = Document(
            document_type=request.document_type,
            identity=DocumentIdentity(
                canonical_name=canonical_name,
                aliases=tuple(sorted(a for a in aliases if a)),
            ),
            explanation="",
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        saved_document = self.documents.save(document)

        return self.upload_new_version(saved_document.id, request)

    def upload_new_version(self, document_id: UUID, request: UploadRequest) -> UploadResult:
        """Upload version to existing document after compatibility checks."""
        document = self.documents.get(document_id)
        if not document:
            raise DomainValidationError(_('Document not found'))

        if not self.permissions.can_upload_version(request.user_id, document):
            raise DomainValidationError(_('Upload is not allowed for the current user'))

        if not request.skip_filename_check and not self.validate_filename_compatibility(
            document, request.source_filename
        ):
            raise DomainValidationError(_('Filename is not compatible with the document identity'))

        file_hash = self.hashing.hash_file(request.file_path)
        duplicate = self.versions.get_by_hash(document.id, file_hash)
        if duplicate is not None:
            return self.handle_duplicate_upload(document.id, file_hash)

        current_versions = self.versions.list_for_document(document.id)
        next_version_number = (max((v.version_number for v in current_versions), default=0) + 1)
        version_id = uuid4()
        from .infra.storage import UserfilesStoragePort

        storage_key = UserfilesStoragePort.version_storage_key(document.id, version_id)
        storage_key = self.storage.save(request.file_path, destination_name=storage_key)

        extractor = self._resolve_metadata_extractor(request.document_type)
        metadata: dict[str, object] = {}
        parse_errors: tuple[str, ...] = ()
        status = VersionStatus.NEW

        if extractor is not None:
            try:
                metadata = extractor.extract(request.file_path)
            except Exception as exc:  # noqa: BLE001 - domain should convert infra failures to state.
                status = VersionStatus.INVALID
                parse_errors = (str(exc),)

        new_version = DocumentVersion(
            id=version_id,
            document_id=document.id,
            status=status,
            version_number=next_version_number,
            source_filename=request.source_filename,
            storage_key=storage_key,
            content_hash=file_hash,
            created_by_user_id=request.user_id,
            change_comment=request.change_comment,
            extracted_metadata=metadata,
            error_messages=parse_errors,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        saved_version = self.versions.save(new_version)

        document.current_version_id = saved_version.id
        document.updated_at = datetime.now()
        self.documents.save(document)

        upload_name = request.source_filename
        if request.link_source_as_alias or request.skip_filename_check:
            canon_meta = ''
            if isinstance(metadata.get('canonical_filename'), str):
                canon_meta = metadata['canonical_filename']
            self._merge_identity_aliases(document, upload_name, canon_meta)

        self._apply_attach_name_policy(
            document=document,
            version=saved_version,
            upload_name=upload_name,
            metadata=metadata,
            name_policy=request.name_policy,
        )
        # Reload after possible rename/policy updates.
        document = self.documents.get(document.id) or document
        saved_version = self.versions.get_active_version(document.id) or saved_version

        if saved_version.status == VersionStatus.INVALID:
            first_error = saved_version.error_messages[0] if saved_version.error_messages else ""
            self.mark_invalid_after_parse_failure(
                document=document,
                version=saved_version,
                parse_error=first_error,
                previous_status=VersionStatus.NEW,
            )

        return UploadResult(
            document_id=document.id,
            version_id=saved_version.id,
            status=saved_version.status.value,
            message=_('Version uploaded'),
        )

    def validate_filename_compatibility(self, document: Document, source_filename: str) -> bool:
        """Guard for 'Upload new version' action."""
        strategy = self._resolve_naming_strategy(document.document_type)
        return strategy.is_compatible(source_filename, document)

    def handle_duplicate_upload(self, document_id: UUID, content_hash: str) -> UploadResult:
        """Idempotency path: no new version, promote existing as current."""
        existing = self.versions.get_by_hash(document_id, content_hash)
        if existing is None:
            raise DomainValidationError(_('Duplicate version was expected but not found'))

        document = self.documents.get(document_id)
        if document is None:
            raise DomainValidationError(_('Document not found'))

        document.current_version_id = existing.id
        document.updated_at = datetime.now()
        self.documents.save(document)

        existing.updated_at = datetime.now()
        self.versions.save(existing)

        return UploadResult(
            document_id=document_id,
            version_id=existing.id,
            status='already_exists',
            message=_('Duplicate upload detected; existing version returned'),
        )

    def set_document_explanation(self, document_id: UUID, explanation: str, actor_user_id: int) -> None:
        document = self.documents.get(document_id)
        if not document:
            raise DomainValidationError(_('Document not found'))
        if not self.permissions.can_edit_document(actor_user_id, document):
            raise DomainValidationError(_('User cannot update the document explanation'))
        document.explanation = explanation.strip()
        document.updated_at = datetime.now()
        self.documents.save(document)

    def apply_plx_canonical_rename(
        self,
        *,
        document_id: UUID,
        field_values: dict[str, str],
        actor_user_id: int,
        allow_large_deviation: bool = False,
        rename_file: bool = True,
    ) -> str:
        """Обновляет метаданные именования, каноническое имя и (опционально) файл на диске."""
        from plans.canonical_edit import (
            apply_naming_values,
            auto_canonical_from_meta,
            build_name_from_naming_values,
            deviation_ok,
            normalize_filename,
            validate_naming_fields,
        )

        document = self.documents.get(document_id)
        if not document:
            raise DomainValidationError(_('Document not found'))
        if document.document_type != DocumentType.PLX:
            raise DomainValidationError(_('Canonical rename is only available for study plans'))
        if not self.permissions.can_upload_version(actor_user_id, document):
            raise DomainValidationError(_('User cannot rename this document'))

        version = self.versions.get_active_version(document.id)
        if version is None:
            raise DomainValidationError(_('Document has no current version'))

        errors = validate_naming_fields(field_values)
        if errors:
            raise DomainValidationError('; '.join(errors))

        proposed = build_name_from_naming_values(field_values)
        meta = dict(version.extracted_metadata or {})
        auto_name = auto_canonical_from_meta(meta)
        if not allow_large_deviation and not deviation_ok(auto_name, proposed):
            raise DomainValidationError(
                _(
                    'Proposed name differs too much from the automatic canonical name. '
                    'Adjust fields or confirm a large deviation.'
                )
            )

        for other in self.documents.list_for_type(DocumentType.PLX):
            if other.id == document.id:
                continue
            names = {normalize_filename(other.identity.canonical_name)}
            names.update(normalize_filename(a) for a in other.identity.aliases)
            if normalize_filename(proposed) in names:
                raise DomainValidationError(
                    _('Name «%(name)s» is already used by another plan') % {'name': proposed}
                )

        old_source = version.source_filename
        old_canonical = document.identity.canonical_name
        new_meta = apply_naming_values(meta, field_values)

        version.extracted_metadata = new_meta
        version.source_filename = proposed
        version.updated_at = datetime.now()
        self.versions.save(version)

        if rename_file:
            self._rename_version_storage_to_basename(document.id, version, proposed)

        document.identity = DocumentIdentity(
            canonical_name=proposed,
            aliases=document.identity.aliases,
        )
        document.updated_at = datetime.now()
        self.documents.save(document)
        self._merge_identity_aliases(document, old_source, old_canonical, proposed)

        return proposed

    def _reclaim_sibling_storage_basename(
        self,
        document_id: UUID,
        current_version: DocumentVersion,
        proposed_basename: str,
    ) -> None:
        """If another version of the same plan owns the target basename, move it back to UUID key."""
        from .infra.storage import UserfilesStoragePort

        proposed_name = Path(proposed_basename).name
        if not proposed_name or not hasattr(self.storage, 'rename'):
            return
        target_key = str(Path(current_version.storage_key).with_name(proposed_name)).replace('\\', '/')
        current_key = (current_version.storage_key or '').replace('\\', '/')
        if target_key == current_key:
            return

        for sibling in self.versions.list_for_document(document_id):
            if sibling.id == current_version.id:
                continue
            sibling_key = (sibling.storage_key or '').replace('\\', '/')
            if sibling_key != target_key:
                continue
            stable_key = UserfilesStoragePort.version_storage_key(document_id, sibling.id)
            stable_basename = Path(stable_key).name
            try:
                new_sibling_key = self.storage.rename(sibling.storage_key, stable_basename)
            except FileExistsError:
                # UUID path already present — drop the conflicting human-named file and point DB to UUID key.
                if hasattr(self.storage, 'delete'):
                    self.storage.delete(sibling.storage_key)
                new_sibling_key = stable_key
            except FileNotFoundError:
                new_sibling_key = stable_key
            sibling.storage_key = new_sibling_key
            sibling.updated_at = datetime.now()
            self.versions.save(sibling)
            break

    def _rename_version_storage_to_basename(
        self,
        document_id: UUID,
        version: DocumentVersion,
        proposed: str,
    ) -> DocumentVersion:
        """Rename version file on disk; reclaim basename from sibling versions of the same plan."""
        if not hasattr(self.storage, 'rename'):
            return version
        proposed_name = Path(proposed).name
        if not proposed_name:
            return version
        self._reclaim_sibling_storage_basename(document_id, version, proposed_name)
        try:
            new_key = self.storage.rename(version.storage_key, proposed_name)
        except FileExistsError as exc:
            raise DomainValidationError(
                _('A file named «%(name)s» already exists in storage') % {'name': proposed_name}
            ) from exc
        except FileNotFoundError as exc:
            raise DomainValidationError(_('Source file was not found in storage')) from exc
        version.storage_key = new_key
        version.updated_at = datetime.now()
        return self.versions.save(version)

    def _apply_attach_name_policy(
        self,
        *,
        document: Document,
        version: DocumentVersion,
        upload_name: str,
        metadata: dict[str, object],
        name_policy: str,
    ) -> None:
        """Apply naming choice after attaching a new version to an existing plan."""
        from plans.canonical_edit import expected_canonical_from_meta, normalize_filename

        policy = name_policy if name_policy in NAME_POLICIES else NAME_POLICY_KEEP_PLAN
        plan_name = (document.identity.canonical_name or '').strip()
        meta = dict(metadata or {})

        if policy == NAME_POLICY_USE_UPLOAD:
            return

        if policy == NAME_POLICY_FROM_METADATA:
            proposed = expected_canonical_from_meta(meta).strip()
            if not proposed:
                return
            old_plan = plan_name
            version.source_filename = proposed
            version.updated_at = datetime.now()
            self.versions.save(version)
            document.identity = DocumentIdentity(
                canonical_name=proposed,
                aliases=document.identity.aliases,
            )
            document.updated_at = datetime.now()
            self.documents.save(document)
            self._merge_identity_aliases(document, upload_name, old_plan, proposed)
            self._rename_version_storage_to_basename(document.id, version, proposed)
            return

        # keep_plan (default): logical name of the new version = existing plan name.
        if not plan_name:
            return
        if normalize_filename(version.source_filename) != normalize_filename(plan_name):
            version.source_filename = plan_name
            version.updated_at = datetime.now()
            self.versions.save(version)
        self._merge_identity_aliases(document, upload_name)
        self._rename_version_storage_to_basename(document.id, version, plan_name)

    def transition_version_status(
        self,
        *,
        version_id: UUID,
        actor_user_id: int,
        target_status: VersionStatus,
        action_comment: str,
        allow_without_comment: bool,
    ) -> DocumentVersion:
        from .workflow_ui import target_status_label

        version = self.versions.get(version_id)
        if version is None:
            raise DomainValidationError(_('Version not found'))

        document = self.documents.get(version.document_id)
        if document is None:
            raise DomainValidationError(_('Parent document not found'))

        if not self.permissions.can_transition(actor_user_id, version, target_status):
            raise DomainValidationError(_('User cannot perform this transition'))

        rule = get_rule(version.status, target_status)
        if rule is None:
            raise DomainValidationError(
                _('Transition %(from_status)s → %(to_status)s is not allowed')
                % {
                    'from_status': target_status_label(version.status),
                    'to_status': target_status_label(target_status),
                }
            )

        normalized_comment = action_comment.strip()
        if rule.requires_comment and not normalized_comment and not allow_without_comment:
            raise DomainValidationError(_('Comment is required for this transition'))

        previous_approved_id: UUID | None = None
        with transaction.atomic():
            if target_status == VersionStatus.APPROVED:
                previous_approved = self.versions.get_approved_version(document.id)
                if previous_approved and previous_approved.id != version.id:
                    self._archive_approved_version(
                        previous_approved,
                        actor_user_id=actor_user_id,
                        action_comment=_('Superseded by a new approved version'),
                    )
                    previous_approved_id = previous_approved.id

            transition = WorkflowTransition(
                document_version_id=version.id,
                from_status=version.status,
                to_status=target_status,
                action=rule.action,
                action_comment=normalized_comment,
                actor_user_id=actor_user_id,
                created_at=datetime.now(),
            )
            self.workflow.save_transition(transition)

            version.status = target_status
            version.updated_at = datetime.now()
            saved_version = self.versions.save(version)

            try:
                from documents.audit import log_action
                from django.contrib.auth import get_user_model

                actor = get_user_model().objects.filter(pk=actor_user_id).first()
                log_action(
                    action=f'workflow_{rule.action.value}',
                    actor=actor,
                    object_type='document_version',
                    object_id=str(version.id),
                    metadata={
                        'from': str(transition.from_status),
                        'to': str(target_status),
                        'document_id': str(document.id),
                    },
                )
            except Exception:  # noqa: BLE001
                pass

            document.current_version_id = saved_version.id
            if target_status == VersionStatus.APPROVED:
                document.approved_version_id = saved_version.id
            document.updated_at = datetime.now()
            self.documents.save(document)

        if target_status == VersionStatus.APPROVED:
            try:
                from external_sync.hooks import on_version_approved

                on_version_approved(
                    document_id=document.id,
                    version_id=saved_version.id,
                    previous_approved_id=previous_approved_id,
                )
            except ImportError:
                pass

        return saved_version

    def import_trusted_plx(
        self,
        *,
        file_path: Path,
        source_filename: str,
        trusted_status: VersionStatus,
        document_id: UUID | None = None,
        actor_user_id: int = SYNC_ACTOR_USER_ID,
        change_comment: str = '',
    ) -> UploadResult:
        """Trusted import from external storage (approved or archived, not draft)."""
        if trusted_status not in (VersionStatus.APPROVED, VersionStatus.ARCHIVED):
            raise DomainValidationError(
                _('Trusted import supports only approved or archived status')
            )

        request = UploadRequest(
            user_id=actor_user_id,
            document_type=DocumentType.PLX,
            file_path=file_path,
            source_filename=source_filename,
            change_comment=change_comment,
            skip_filename_check=True,
            link_source_as_alias=True,
        )

        if document_id is None:
            suggestions = self.suggest_document_matches(request).suggestions
            exact = [s for s in suggestions if s.reason in ('filename_exact', 'canonical_exact')]
            if len(exact) == 1:
                document_id = exact[0].document_id
            elif len(exact) > 1:
                return UploadResult(
                    document_id=exact[0].document_id,
                    version_id=None,
                    status='ambiguous_match',
                    message=_('Ambiguous match; manual review required'),
                )

        file_hash = self.hashing.hash_file(file_path)

        if document_id is not None:
            duplicate = self.versions.get_by_hash(document_id, file_hash)
            if duplicate is not None:
                document = self.documents.get(document_id)
                if document and trusted_status == VersionStatus.APPROVED:
                    document.current_version_id = duplicate.id
                    document.approved_version_id = duplicate.id
                    document.updated_at = datetime.now()
                    self.documents.save(document)
                return UploadResult(
                    document_id=document_id,
                    version_id=duplicate.id,
                    status='already_exists',
                    message=_('Duplicate content; existing version returned'),
                )

        with transaction.atomic():
            if document_id is None:
                document = self._create_trusted_document(request, file_hash, trusted_status)
            else:
                document = self.documents.get(document_id)
                if document is None:
                    raise DomainValidationError(_('Document not found'))
                saved_version = self._create_trusted_version(
                    document=document,
                    request=request,
                    file_hash=file_hash,
                    trusted_status=trusted_status,
                    actor_user_id=actor_user_id,
                )
                document = self.documents.get(document.id)
                if document is None:
                    raise DomainValidationError(_('Document not found'))
                return UploadResult(
                    document_id=document.id,
                    version_id=saved_version.id,
                    status=saved_version.status.value,
                    message=_('Trusted version imported'),
                )

        return UploadResult(
            document_id=document.id,
            version_id=document.current_version_id,
            status=trusted_status.value,
            message=_('Trusted document imported'),
        )

    def _create_trusted_document(
        self,
        request: UploadRequest,
        file_hash: str,
        trusted_status: VersionStatus,
    ) -> Document:
        strategy = self._resolve_naming_strategy(request.document_type)
        canonical_name = strategy.canonicalize(request.source_filename)
        aliases = set(strategy.build_aliases(request.source_filename))
        extractor = self._resolve_metadata_extractor(request.document_type)
        metadata: dict[str, object] = {}
        if extractor is not None:
            try:
                metadata = extractor.extract(request.file_path)
            except Exception:  # noqa: BLE001
                metadata = {}
            canon_from_meta = (metadata or {}).get('canonical_filename')
            if isinstance(canon_from_meta, str) and canon_from_meta.strip():
                canonical_name = canon_from_meta.strip()
                aliases.add(canonical_name)
                aliases.add(Path(canonical_name).name)

        document = Document(
            document_type=request.document_type,
            identity=DocumentIdentity(
                canonical_name=canonical_name,
                aliases=tuple(sorted(a for a in aliases if a)),
            ),
            explanation='',
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        saved_document = self.documents.save(document)
        self._create_trusted_version(
            document=saved_document,
            request=request,
            file_hash=file_hash,
            trusted_status=trusted_status,
            actor_user_id=request.user_id,
            metadata=metadata,
        )
        refreshed = self.documents.get(saved_document.id)
        if refreshed is None:
            raise DomainValidationError(_('Document not found'))
        return refreshed

    def _create_trusted_version(
        self,
        *,
        document: Document,
        request: UploadRequest,
        file_hash: str,
        trusted_status: VersionStatus,
        actor_user_id: int,
        metadata: dict[str, object] | None = None,
    ) -> DocumentVersion:
        from .infra.storage import UserfilesStoragePort

        if trusted_status == VersionStatus.APPROVED:
            previous_approved = self.versions.get_approved_version(document.id)
            if previous_approved:
                self._archive_approved_version(
                    previous_approved,
                    actor_user_id=actor_user_id,
                    action_comment=_('Superseded by trusted external import'),
                )

        current_versions = self.versions.list_for_document(document.id)
        next_version_number = (max((v.version_number for v in current_versions), default=0) + 1)
        version_id = uuid4()
        storage_key = UserfilesStoragePort.version_storage_key(document.id, version_id)
        storage_key = self.storage.save(request.file_path, destination_name=storage_key)

        if metadata is None:
            metadata = {}
            extractor = self._resolve_metadata_extractor(request.document_type)
            if extractor is not None:
                try:
                    metadata = extractor.extract(request.file_path)
                except Exception:  # noqa: BLE001
                    metadata = {}

        new_version = DocumentVersion(
            id=version_id,
            document_id=document.id,
            status=trusted_status,
            version_number=next_version_number,
            source_filename=request.source_filename,
            storage_key=storage_key,
            content_hash=file_hash,
            created_by_user_id=actor_user_id,
            change_comment=request.change_comment,
            extracted_metadata=metadata,
            error_messages=(),
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        saved_version = self.versions.save(new_version)

        transition = WorkflowTransition(
            document_version_id=saved_version.id,
            from_status=VersionStatus.NEW,
            to_status=trusted_status,
            action=WorkflowAction.APPROVE if trusted_status == VersionStatus.APPROVED else WorkflowAction.ARCHIVE,
            action_comment=_('Trusted import from external storage'),
            actor_user_id=actor_user_id,
            created_at=datetime.now(),
        )
        self.workflow.save_transition(transition)

        document.current_version_id = saved_version.id
        if trusted_status == VersionStatus.APPROVED:
            document.approved_version_id = saved_version.id
        document.updated_at = datetime.now()
        self.documents.save(document)
        self._merge_identity_aliases(document, request.source_filename)
        return saved_version

    def _archive_approved_version(
        self,
        version: DocumentVersion,
        *,
        actor_user_id: int,
        action_comment: str,
    ) -> DocumentVersion:
        if version.status != VersionStatus.APPROVED:
            return version
        transition = WorkflowTransition(
            document_version_id=version.id,
            from_status=version.status,
            to_status=VersionStatus.ARCHIVED,
            action=WorkflowAction.ARCHIVE,
            action_comment=action_comment,
            actor_user_id=actor_user_id,
            created_at=datetime.now(),
        )
        self.workflow.save_transition(transition)
        version.status = VersionStatus.ARCHIVED
        version.updated_at = datetime.now()
        saved = self.versions.save(version)
        document = self.documents.get(version.document_id)
        if document and document.approved_version_id == version.id:
            document.approved_version_id = None
            document.updated_at = datetime.now()
            self.documents.save(document)
        return saved

    def add_discussion_message(
        self, *, version_id: UUID, author_user_id: int, message: str
    ) -> DiscussionMessage:
        version = self.versions.get(version_id)
        if version is None:
            raise DomainValidationError(_('Version not found'))
        thread = self.discussions.get_or_create_thread(version_id)
        msg = DiscussionMessage(
            thread_id=thread.id,
            author_user_id=author_user_id,
            message=message.strip(),
            created_at=datetime.now(),
        )
        return self.discussions.add_message(msg)

    def mark_invalid_after_parse_failure(
        self,
        *,
        document: Document,
        version: DocumentVersion,
        parse_error: str = "",
        previous_status: VersionStatus | None = None,
    ) -> DocumentVersion:
        """Utility for parse failure workflow path.

        Keeps uploaded artifact while marking the version as invalid.
        """
        from_status = previous_status or version.status
        version.status = VersionStatus.INVALID
        if parse_error:
            version.error_messages = tuple([*version.error_messages, parse_error])
        version.updated_at = datetime.now()
        saved = self.versions.save(version)

        transition = WorkflowTransition(
            document_version_id=version.id,
            from_status=from_status,
            to_status=VersionStatus.INVALID,
            action=WorkflowAction.MARK_INVALID,
            action_comment=_('Metadata extraction failed'),
            actor_user_id=version.created_by_user_id,
            created_at=datetime.now(),
        )
        self.workflow.save_transition(transition)
        return saved

    def hard_delete_document(self, *, document_id: UUID, actor_user_id: int) -> None:
        """Безвозвратное удаление документа, версий и файлов в USERFILES_ROOT."""
        from documents import models as orm
        from documents.audit import log_action

        document = self.documents.get(document_id)
        if document is None:
            raise DomainValidationError(_('Document not found'))

        if not self.permissions.can_hard_delete(actor_user_id, document):
            raise DomainValidationError(_('Hard delete is not allowed for the current user'))

        record = orm.Document.objects.filter(pk=document_id).prefetch_related('versions').first()
        if record is None:
            raise DomainValidationError(_('Document not found'))

        storage_keys = [v.storage_key for v in record.versions.all() if v.storage_key]
        canonical = record.canonical_name
        record_id = str(record.pk)

        record.delete()

        for key in storage_keys:
            try:
                self.storage.delete(key)
            except OSError:
                pass

        from django.contrib.auth import get_user_model

        actor = get_user_model().objects.filter(pk=actor_user_id).first()
        log_action(
            action=WorkflowAction.HARD_DELETE.value,
            actor=actor,
            object_type='document',
            object_id=record_id,
            metadata={'canonical_name': canonical, 'storage_keys': storage_keys},
        )
