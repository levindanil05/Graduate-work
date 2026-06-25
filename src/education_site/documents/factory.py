from __future__ import annotations

from documents.infra.extractors import PlxMetadataExtractor
from documents.infra.hashing import HashingService
from documents.infra.storage import UserfilesStoragePort
from documents.permissions import AllowAllPermissionService
from documents.repos.django_repos import (
    DjangoDiscussionRepository,
    DjangoDocumentRepository,
    DjangoVersionRepository,
    DjangoWorkflowRepository,
)
from documents.services import DocumentApplicationService
from documents.strategies import GenericNamingStrategy, PlxNamingStrategy


def build_document_service() -> DocumentApplicationService:
    return DocumentApplicationService(
        documents=DjangoDocumentRepository(),
        versions=DjangoVersionRepository(),
        workflow=DjangoWorkflowRepository(),
        discussions=DjangoDiscussionRepository(),
        storage=UserfilesStoragePort(),
        hashing=HashingService(),
        metadata_extractors=[PlxMetadataExtractor()],
        naming_strategies=[PlxNamingStrategy(), GenericNamingStrategy()],
        permissions=AllowAllPermissionService(),
    )
