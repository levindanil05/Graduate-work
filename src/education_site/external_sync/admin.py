from __future__ import annotations

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms import ModelForm

from external_sync.models import (
    ExternalConnection,
    ExternalReplica,
    ExternalSyncSettings,
    OutboundIntent,
    RemoteObjectSnapshot,
    SwitchAuditLog,
    SyncConflict,
    SyncRun,
    WriteMode,
)


def _audit_switch(instance, field: str, old, new, connection=None) -> None:
    if old == new:
        return
    SwitchAuditLog.objects.create(
        setting_name=field,
        connection=connection,
        old_value=str(old),
        new_value=str(new),
    )


class ExternalConnectionForm(ModelForm):
    class Meta:
        model = ExternalConnection
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        write_mode = cleaned.get('write_mode')
        push_enabled = cleaned.get('push_enabled')
        pull_enabled = cleaned.get('pull_enabled')
        if write_mode == WriteMode.READ_ONLY and push_enabled:
            cleaned['push_enabled'] = False
        if pull_enabled:
            others = ExternalConnection.objects.filter(pull_enabled=True)
            if self.instance.pk:
                others = others.exclude(pk=self.instance.pk)
            if others.exists():
                raise ValidationError(
                    'Получение изменений уже включено для другого подключения. '
                    'Сначала выключите его там.'
                )
        return cleaned


@admin.register(ExternalSyncSettings)
class ExternalSyncSettingsAdmin(admin.ModelAdmin):
    list_display = ('external_sync_enabled', 'updated_at')

    def save_model(self, request, obj, form, change):
        if change:
            old = ExternalSyncSettings.objects.get(pk=obj.pk)
            _audit_switch(
                obj,
                'external_sync_enabled',
                old.external_sync_enabled,
                obj.external_sync_enabled,
            )
        super().save_model(request, obj, form, change)


@admin.register(ExternalConnection)
class ExternalConnectionAdmin(admin.ModelAdmin):
    form = ExternalConnectionForm
    list_display = (
        'name',
        'slug',
        'write_mode',
        'enabled',
        'pull_enabled',
        'push_enabled',
        'last_checkpoint_at',
    )
    list_filter = ('write_mode', 'enabled', 'pull_enabled', 'push_enabled')
    search_fields = ('name', 'slug')
    readonly_fields = ('last_checkpoint_at', 'lease_token', 'lease_until', 'created_at', 'updated_at')

    def save_model(self, request, obj, form, change):
        if obj.write_mode == WriteMode.READ_ONLY:
            obj.push_enabled = False
        if obj.pull_enabled:
            ExternalConnection.objects.exclude(pk=obj.pk).update(pull_enabled=False)
        if change:
            old = ExternalConnection.objects.get(pk=obj.pk)
            for field in ('enabled', 'pull_enabled', 'push_enabled', 'schedule_enabled', 'manual_run_enabled'):
                _audit_switch(obj, field, getattr(old, field), getattr(obj, field), connection=obj)
        super().save_model(request, obj, form, change)


@admin.register(RemoteObjectSnapshot)
class RemoteObjectSnapshotAdmin(admin.ModelAdmin):
    list_display = ('connection', 'remote_path', 'role', 'content_hash', 'updated_at')
    list_filter = ('connection', 'role')
    search_fields = ('remote_path',)


@admin.register(ExternalReplica)
class ExternalReplicaAdmin(admin.ModelAdmin):
    list_display = ('connection', 'remote_path', 'role', 'sync_state', 'is_primary', 'last_reconciled_at')
    list_filter = ('connection', 'role', 'sync_state')
    search_fields = ('remote_path',)


@admin.register(SyncRun)
class SyncRunAdmin(admin.ModelAdmin):
    list_display = (
        'connection',
        'status',
        'imported_count',
        'published_count',
        'duplicates_count',
        'errors_count',
        'finished_at',
    )
    list_filter = ('status', 'connection')
    readonly_fields = ('report_lines',)


@admin.register(OutboundIntent)
class OutboundIntentAdmin(admin.ModelAdmin):
    list_display = ('connection', 'kind', 'status', 'version', 'desired_remote_path', 'updated_at')
    list_filter = ('connection', 'kind', 'status')


@admin.register(SyncConflict)
class SyncConflictAdmin(admin.ModelAdmin):
    list_display = ('connection', 'remote_path', 'resolved', 'created_at')
    list_filter = ('connection', 'resolved')


@admin.register(SwitchAuditLog)
class SwitchAuditLogAdmin(admin.ModelAdmin):
    list_display = ('setting_name', 'connection', 'old_value', 'new_value', 'created_at')
    list_filter = ('setting_name', 'connection')
    readonly_fields = ('setting_name', 'connection', 'old_value', 'new_value', 'actor_id', 'created_at')
