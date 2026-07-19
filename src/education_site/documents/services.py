from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID

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
        storage_key = self.storage.save(request.file_path, destination_name=request.source_filename)

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

        if request.link_source_as_alias or request.skip_filename_check:
            canon_meta = ''
            if isinstance(metadata.get('canonical_filename'), str):
                canon_meta = metadata['canonical_filename']
            self._merge_identity_aliases(document, request.source_filename, canon_meta)

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
        if not self.permissions.can_upload_version(actor_user_id, document):
            raise DomainValidationError(_('User cannot update the document explanation'))
        document.explanation = explanation.strip()
        document.updated_at = datetime.now()
        self.documents.save(document)

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
        return self.versions.save(version)

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
