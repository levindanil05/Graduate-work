from __future__ import annotations

from dataclasses import dataclass

from .contracts import DocumentNamingStrategy
from .entities import Document, DocumentType, NameMatchResult


@dataclass
class PlxNamingStrategy(DocumentNamingStrategy):
    """Naming strategy example for PLX documents.

    Real transliteration/rename rules are intentionally omitted for now.
    """

    def supports(self, document_type: DocumentType) -> bool:
        return document_type == DocumentType.PLX

    def canonicalize(self, filename: str) -> str:
        raise NotImplementedError

    def build_aliases(self, filename: str) -> tuple[str, ...]:
        raise NotImplementedError

    def is_compatible(self, filename: str, document: Document) -> bool:
        raise NotImplementedError

    def find_match(self, filename: str, candidates: list[Document]) -> NameMatchResult:
        raise NotImplementedError


@dataclass
class GenericNamingStrategy(DocumentNamingStrategy):
    """Fallback strategy for generic documents."""

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


class NamingStrategyRegistry:
    def __init__(self, strategies: list[DocumentNamingStrategy]) -> None:
        self._strategies = strategies

    def resolve(self, document_type: DocumentType) -> DocumentNamingStrategy:
        for strategy in self._strategies:
            if strategy.supports(document_type):
                return strategy
        raise LookupError(f"No naming strategy for document type: {document_type}")

