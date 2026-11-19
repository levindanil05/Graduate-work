"""Proposed database schema (discussion draft, not wired to runtime)."""

from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DocumentRecord(TimestampedModel):
    document_type = models.CharField(max_length=80, db_index=True)
    canonical_name = models.CharField(max_length=255, db_index=True)
    explanation = models.TextField(blank=True, default="")
    extra_data = models.JSONField(default=dict, blank=True)
    current_version = models.ForeignKey(
        "DocumentVersionRecord",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )

    class Meta:
        db_table = "document_record"


class DocumentAliasRecord(models.Model):
    document = models.ForeignKey(DocumentRecord, on_delete=models.CASCADE, related_name="aliases")
    alias = models.CharField(max_length=255, db_index=True, unique=True)
    alias_source = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "document_alias_record"


class DocumentVersionRecord(TimestampedModel):
    document = models.ForeignKey(DocumentRecord, on_delete=models.CASCADE, related_name="versions")
    status = models.CharField(max_length=32, db_index=True)
    version_number = models.PositiveIntegerField()
    source_filename = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=500)
    content_hash = models.CharField(max_length=128, db_index=True)
    change_comment = models.TextField(blank=True, default="")
    extracted_metadata = models.JSONField(default=dict, blank=True)
    error_messages = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "document_version_record"
        constraints = [
            models.UniqueConstraint(
                fields=["document", "version_number"],
                name="uniq_document_version_number",
            )
        ]


class DiscussionThreadRecord(TimestampedModel):
    document_version = models.OneToOneField(
        DocumentVersionRecord,
        on_delete=models.CASCADE,
        related_name="discussion_thread",
    )

    class Meta:
        db_table = "discussion_thread_record"


class DiscussionMessageRecord(TimestampedModel):
    thread = models.ForeignKey(
        DiscussionThreadRecord,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    author_id = models.IntegerField(null=True, blank=True)
    after_message_id = models.UUIDField(null=True, blank=True)
    replies_to_message_id = models.UUIDField(null=True, blank=True)
    message = models.TextField()

    class Meta:
        db_table = "discussion_message_record"


class WorkflowTransitionRecord(TimestampedModel):
    document_version = models.ForeignKey(
        DocumentVersionRecord,
        on_delete=models.CASCADE,
        related_name="workflow_transitions",
    )
    from_status = models.CharField(max_length=32)
    to_status = models.CharField(max_length=32)
    action = models.CharField(max_length=64)
    action_comment = models.TextField(blank=True, default="")
    actor_id = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "workflow_transition_record"


class DocumentTypeStrategyRecord(models.Model):
    """Links type -> naming/extractor policy keys."""

    document_type = models.CharField(max_length=80, unique=True)
    naming_strategy_key = models.CharField(max_length=120)
    rename_policy_key = models.CharField(max_length=120, blank=True, default="")
    metadata_extractor_key = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        db_table = "document_type_strategy_record"

