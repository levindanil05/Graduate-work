from django import forms
from django.contrib import admin

from documents.document_types import list_specs

from .audit import ActionLog
from .models import (
    DiscussionMessage,
    DiscussionThread,
    Document,
    DocumentAlias,
    DocumentTypeStrategy,
    DocumentVersion,
    WorkflowTransition,
)


class DocumentAdminForm(forms.ModelForm):
    class Meta:
        model = Document
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        choices = [('', '---------'), *[(spec.code, spec.label) for spec in list_specs()]]
        current = getattr(self.instance, 'document_type', '') or ''
        if current and current not in {code for code, _label in choices}:
            choices.append((current, current))
        self.fields['document_type'].widget = forms.Select(choices=choices)


class DocumentAliasInline(admin.TabularInline):
    model = DocumentAlias
    extra = 0


class DocumentVersionInline(admin.TabularInline):
    model = DocumentVersion
    extra = 0
    fields = (
        'version_number',
        'status',
        'source_filename',
        'storage_key',
        'content_hash',
        'updated_at',
    )
    readonly_fields = ('updated_at',)
    show_change_link = True


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    form = DocumentAdminForm
    list_display = ('canonical_name', 'document_type', 'current_version', 'updated_at')
    list_filter = ('document_type',)
    search_fields = ('canonical_name', 'aliases__alias')
    inlines = (DocumentAliasInline, DocumentVersionInline)


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    list_display = (
        'source_filename',
        'document',
        'version_number',
        'status',
        'storage_key',
        'updated_at',
    )
    list_filter = ('status',)
    search_fields = ('source_filename', 'storage_key', 'document__canonical_name')


admin.site.register(DiscussionThread)
admin.site.register(DiscussionMessage)
admin.site.register(WorkflowTransition)
admin.site.register(DocumentTypeStrategy)


@admin.register(ActionLog)
class ActionLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'action', 'actor', 'object_type', 'object_id')
    list_filter = ('action', 'object_type')
    search_fields = ('object_id', 'action', 'metadata')
    readonly_fields = ('created_at',)
