from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from .entities import DiscussionMessage, DiscussionThread, Document, DocumentVersion


@dataclass(frozen=True)
class LinkIssue:
    entity: str
    entity_id: UUID | None
    message: str


def validate_document_links(
    *,
    document: Document,
    versions: list[DocumentVersion],
    threads: list[DiscussionThread],
    messages: list[DiscussionMessage],
) -> list[LinkIssue]:
    """Checks internal references without touching persistence layer.

    Useful during early design and later for test fixtures:
    - all versions must belong to one document;
    - current_version_id should point to an existing version;
    - each thread must point to existing version;
    - each message must point to existing thread.
    """

    issues: list[LinkIssue] = []

    version_ids = {v.id for v in versions}
    thread_ids = {t.id for t in threads}

    for version in versions:
        if version.document_id != document.id:
            issues.append(
                LinkIssue(
                    entity="DocumentVersion",
                    entity_id=version.id,
                    message="version.document_id does not match document.id",
                )
            )

    if document.current_version_id and document.current_version_id not in version_ids:
        issues.append(
            LinkIssue(
                entity="Document",
                entity_id=document.id,
                message="current_version_id points to non-existing version",
            )
        )

    for thread in threads:
        if thread.document_version_id not in version_ids:
            issues.append(
                LinkIssue(
                    entity="DiscussionThread",
                    entity_id=thread.id,
                    message="thread points to non-existing version",
                )
            )

    for message in messages:
        if message.thread_id not in thread_ids:
            issues.append(
                LinkIssue(
                    entity="DiscussionMessage",
                    entity_id=message.id,
                    message="message points to non-existing thread",
                )
            )

    return issues

