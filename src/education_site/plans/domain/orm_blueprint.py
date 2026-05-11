"""Draft ORM model layout for discussion.

This module is not wired into Django app runtime yet.
It provides a concrete data model proposal with contracts in mind.
"""

from django.db import models


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class DocumentRecord(TimestampedModel):
    class Status(models.TextChoices):
        NEW = "new", "Новый"
        ON_REVIEW = "on_review", "На проверке"
        NEEDS_FIX = "needs_fix", "На доработке"
        APPROVED = "approved", "Утвержден"
        ARCHIVED = "archived", "Архивирован"
        INVALID = "invalid", "Ошибочен"
        TRASHED = "trashed", "В корзине"

    # Generic type, e.g. "study_plan", "work_program", "generic".
    document_type = models.CharField(max_length=80, db_index=True)
    canonical_name = models.CharField(max_length=255, db_index=True)
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.NEW)

    # Global explanation is always shown with current version in UI.
    description = models.TextField(blank=True, default="")
    # Non-indexed low-frequency attributes.
    extra_data = models.JSONField(default=dict, blank=True)

    # Active/current version pointer for fast reads.
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
    # Helps debugging where alias came from (translit, legacy, manual, etc.).
    alias_source = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "document_alias_record"


class DocumentVersionRecord(TimestampedModel):
    document = models.ForeignKey(DocumentRecord, on_delete=models.CASCADE, related_name="versions")
    version_number = models.PositiveIntegerField()
    source_filename = models.CharField(max_length=255)
    storage_key = models.CharField(max_length=500)
    content_hash = models.CharField(max_length=128, db_index=True)
    change_comment = models.TextField(blank=True, default="")
    extracted_metadata = models.JSONField(default=dict, blank=True)
    parse_error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "document_version_record"
        constraints = (
            models.UniqueConstraint(
                fields=["document", "version_number"],
                name="uniq_document_version_number",
            ),
        )


class DiscussionMessageRecord(TimestampedModel):
    version = models.ForeignKey(
        DocumentVersionRecord,
        on_delete=models.CASCADE,
        related_name="discussion_messages",
    )
    author_id = models.IntegerField(null=True, blank=True)
    message = models.TextField()

    class Meta:
        db_table = "discussion_message_record"


class WorkflowTransitionRecord(TimestampedModel):
    document = models.ForeignKey(
        DocumentRecord,
        on_delete=models.CASCADE,
        related_name="workflow_transitions",
    )
    from_status = models.CharField(max_length=32)
    to_status = models.CharField(max_length=32)
    action = models.CharField(max_length=64, blank=True, default="")
    action_comment = models.TextField(blank=True, default="")
    actor_id = models.IntegerField(null=True, blank=True)

    class Meta:
        db_table = "workflow_transition_record"


class DocumentTypeStrategyRecord(models.Model):
    """Per document type strategy registry (contracts-level configuration)."""

    document_type = models.CharField(max_length=80, unique=True)
    alias_strategy_key = models.CharField(max_length=120)
    rename_policy_key = models.CharField(max_length=120, blank=True, default="")
    metadata_extractor_key = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        db_table = "document_type_strategy_record"

