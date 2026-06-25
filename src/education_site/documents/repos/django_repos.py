from __future__ import annotations

from datetime import datetime
from uuid import UUID

from documents import models as orm
from documents.entities import (
    DiscussionMessage,
    DiscussionThread,
    Document,
    DocumentIdentity,
    DocumentType,
    DocumentVersion,
    VersionStatus,
    WorkflowAction,
    WorkflowTransition,
)


def _to_domain_document(record: orm.Document) -> Document:
    aliases = tuple(record.aliases.values_list('alias', flat=True))
    return Document(
        id=record.id,
        document_type=DocumentType(record.document_type),
        identity=DocumentIdentity(
            canonical_name=record.canonical_name,
            aliases=aliases,
        ),
        explanation=record.explanation,
        extra_data=dict(record.extra_data or {}),
        current_version_id=record.current_version_id,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_domain_version(record: orm.DocumentVersion) -> DocumentVersion:
    return DocumentVersion(
        id=record.id,
        document_id=record.document_id,
        status=VersionStatus(record.status),
        version_number=record.version_number,
        source_filename=record.source_filename,
        storage_key=record.storage_key,
        content_hash=record.content_hash,
        created_by_user_id=record.created_by_user_id,
        change_comment=record.change_comment,
        extracted_metadata=dict(record.extracted_metadata or {}),
        error_messages=tuple(record.error_messages or []),
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


class DjangoDocumentRepository:
    def get(self, document_id: UUID) -> Document | None:
        try:
            return _to_domain_document(orm.Document.objects.prefetch_related('aliases').get(pk=document_id))
        except orm.Document.DoesNotExist:
            return None

    def save(self, document: Document) -> Document:
        record, _ = orm.Document.objects.update_or_create(
            pk=document.id,
            defaults={
                'document_type': document.document_type.value,
                'canonical_name': document.identity.canonical_name,
                'explanation': document.explanation,
                'extra_data': document.extra_data,
                'current_version_id': document.current_version_id,
            },
        )
        desired_aliases = set(document.identity.aliases)
        record.aliases.exclude(alias__in=desired_aliases).delete()
        for alias in desired_aliases:
            orm.DocumentAlias.objects.get_or_create(document=record, alias=alias)
        document.updated_at = record.updated_at
        return _to_domain_document(record)

    def list_for_type(self, document_type: DocumentType) -> list[Document]:
        qs = orm.Document.objects.filter(document_type=document_type.value).prefetch_related('aliases')
        return [_to_domain_document(record) for record in qs]


class DjangoVersionRepository:
    def save(self, version: DocumentVersion) -> DocumentVersion:
        record, _ = orm.DocumentVersion.objects.update_or_create(
            pk=version.id,
            defaults={
                'document_id': version.document_id,
                'status': version.status.value,
                'version_number': version.version_number,
                'source_filename': version.source_filename,
                'storage_key': version.storage_key,
                'content_hash': version.content_hash,
                'created_by_user_id': version.created_by_user_id,
                'change_comment': version.change_comment,
                'extracted_metadata': version.extracted_metadata,
                'error_messages': list(version.error_messages),
            },
        )
        version.updated_at = record.updated_at
        return _to_domain_version(record)

    def get(self, version_id: UUID) -> DocumentVersion | None:
        try:
            return _to_domain_version(orm.DocumentVersion.objects.get(pk=version_id))
        except orm.DocumentVersion.DoesNotExist:
            return None

    def get_active_version(self, document_id: UUID) -> DocumentVersion | None:
        try:
            document = orm.Document.objects.select_related('current_version').get(pk=document_id)
        except orm.Document.DoesNotExist:
            return None
        if document.current_version_id is None:
            return None
        return _to_domain_version(document.current_version)

    def get_by_hash(self, document_id: UUID, content_hash: str) -> DocumentVersion | None:
        record = (
            orm.DocumentVersion.objects.filter(document_id=document_id, content_hash=content_hash)
            .order_by('-version_number')
            .first()
        )
        return _to_domain_version(record) if record else None

    def list_for_document(self, document_id: UUID) -> list[DocumentVersion]:
        qs = orm.DocumentVersion.objects.filter(document_id=document_id).order_by('version_number')
        return [_to_domain_version(record) for record in qs]


class DjangoWorkflowRepository:
    def save_transition(self, transition: WorkflowTransition) -> WorkflowTransition:
        orm.WorkflowTransition.objects.update_or_create(
            pk=transition.id,
            defaults={
                'document_version_id': transition.document_version_id,
                'from_status': transition.from_status.value,
                'to_status': transition.to_status.value,
                'action': transition.action.value,
                'action_comment': transition.action_comment,
                'actor_id': transition.actor_user_id,
            },
        )
        return transition

    def list_for_version(self, version_id: UUID) -> list[WorkflowTransition]:
        qs = orm.WorkflowTransition.objects.filter(document_version_id=version_id).order_by('created_at')
        return [
            WorkflowTransition(
                id=record.id,
                document_version_id=record.document_version_id,
                from_status=VersionStatus(record.from_status),
                to_status=VersionStatus(record.to_status),
                action=WorkflowAction(record.action),
                action_comment=record.action_comment,
                actor_user_id=record.actor_id,
                created_at=record.created_at,
            )
            for record in qs
        ]


class DjangoDiscussionRepository:
    def get_or_create_thread(self, version_id: UUID) -> DiscussionThread:
        record, created = orm.DiscussionThread.objects.get_or_create(document_version_id=version_id)
        return DiscussionThread(
            id=record.id,
            document_version_id=record.document_version_id,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def add_message(self, message: DiscussionMessage) -> DiscussionMessage:
        orm.DiscussionMessage.objects.update_or_create(
            pk=message.id,
            defaults={
                'thread_id': message.thread_id,
                'author_id': message.author_user_id,
                'after_message_id': message.after_message_id,
                'replies_to_message_id': message.replies_to_message_id,
                'message': message.message,
            },
        )
        return message

    def list_messages(self, thread_id: UUID) -> list[DiscussionMessage]:
        qs = orm.DiscussionMessage.objects.filter(thread_id=thread_id).order_by('created_at')
        return [
            DiscussionMessage(
                id=record.id,
                thread_id=record.thread_id,
                author_user_id=record.author_id,
                after_message_id=record.after_message_id,
                replies_to_message_id=record.replies_to_message_id,
                message=record.message,
                created_at=record.created_at,
            )
            for record in qs
        ]
