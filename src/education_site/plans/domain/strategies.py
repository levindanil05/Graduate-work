from __future__ import annotations

from dataclasses import dataclass

from .contracts import NameAliasStrategy
from .entities import Document, DocumentType, NameMatchResult


@dataclass(slots=True)
class StudyPlanAliasStrategy(NameAliasStrategy):
    """Example strategy for study plans.

    Real normalization/transliteration rules are intentionally omitted.
    """

    def supports(self, document_type: DocumentType) -> bool:
        return document_type == DocumentType.STUDY_PLAN

    def canonicalize(self, filename: str) -> str:
        raise NotImplementedError

    def build_aliases(self, filename: str) -> tuple[str, ...]:
        raise NotImplementedError

    def is_compatible(self, filename: str, document: Document) -> bool:
        raise NotImplementedError

    def find_match(self, filename: str, candidates: list[Document]) -> NameMatchResult:
        raise NotImplementedError


@dataclass(slots=True)
class GenericDocumentAliasStrategy(NameAliasStrategy):
    """Fallback strategy for other document types."""

    def supports(self, document_type: DocumentType) -> bool:
        return document_type == DocumentType.GENERIC

    def canonicalize(self, filename: str) -> str:
        raise NotImplementedError

    def build_aliases(self, filename: str) -> tuple[str, ...]:
        raise NotImplementedError

    def is_compatible(self, filename: str, document: Document) -> bool:
        raise NotImplementedError

    def find_match(self, filename: str, candidates: list[Document]) -> NameMatchResult:
        raise NotImplementedError


class AliasStrategyRegistry:
    """Simple contract-level registry for per-type strategy resolution."""

    def __init__(self, strategies: list[NameAliasStrategy]) -> None:
        self._strategies = strategies

    def resolve(self, document_type: DocumentType) -> NameAliasStrategy:
        for strategy in self._strategies:
            if strategy.supports(document_type):
                return strategy
        raise LookupError(f"No alias strategy registered for document type: {document_type}")

