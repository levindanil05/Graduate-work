from django.contrib import admin

from .models import (
    DiscussionMessage,
    DiscussionThread,
    Document,
    DocumentAlias,
    DocumentTypeStrategy,
    DocumentVersion,
    WorkflowTransition,
)


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
