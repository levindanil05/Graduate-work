from django.contrib import admin

from .models import FeedbackReport


@admin.register(FeedbackReport)
class FeedbackReportAdmin(admin.ModelAdmin):
    list_display = ('subject', 'kind', 'status', 'author', 'created_at', 'handled_by')
    list_filter = ('kind', 'status', 'created_at')
    search_fields = ('subject', 'body', 'author__username')
    readonly_fields = ('created_at', 'context')
    raw_id_fields = ('author', 'document', 'handled_by')
