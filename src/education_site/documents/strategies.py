from __future__ import annotations

from pathlib import Path

from documents.entities import Document, DocumentType, NameMatchResult


def _normalize_filename(filename: str) -> str:
    return Path(filename).name.lower().strip()


def _build_alias_set(filename: str) -> tuple[str, ...]:
    base = Path(filename).name
    stem = Path(base).stem
    aliases = {
        _normalize_filename(base),
        _normalize_filename(stem),
        base,
        filename,
        Path(filename).as_posix(),
    }
    return tuple(sorted(alias for alias in aliases if alias))


class PlxNamingStrategy:
    def supports(self, document_type: DocumentType) -> bool:
        return document_type == DocumentType.PLX

    def canonicalize(self, filename: str) -> str:
        return _normalize_filename(filename)

    def build_aliases(self, filename: str) -> tuple[str, ...]:
        return _build_alias_set(filename)

    def is_compatible(self, filename: str, document: Document) -> bool:
        norm = _normalize_filename(filename)
        if norm == _normalize_filename(document.identity.canonical_name):
            return True
        return norm in {_normalize_filename(alias) for alias in document.identity.aliases}

    def find_match(self, filename: str, candidates: list[Document]) -> NameMatchResult:
        norm = _normalize_filename(filename)
        for document in candidates:
            if norm == _normalize_filename(document.identity.canonical_name):
                return NameMatchResult(
                    matched_document_id=document.id,
                    confidence=1.0,
                    matched_alias=document.identity.canonical_name,
                )
            for alias in document.identity.aliases:
                if norm == _normalize_filename(alias):
                    return NameMatchResult(
                        matched_document_id=document.id,
                        confidence=1.0,
                        matched_alias=alias,
                    )
        closest: list = []
        for document in candidates:
            key = _normalize_filename(document.identity.canonical_name)
            if norm in key or key in norm:
                closest.append(document.id)
        return NameMatchResult(
            matched_document_id=None,
            confidence=0.0,
            closest_document_ids=tuple(closest[:5]),
        )


class GenericNamingStrategy:
    def supports(self, document_type: DocumentType) -> bool:
        return document_type == DocumentType.GENERIC

    def canonicalize(self, filename: str) -> str:
        return _normalize_filename(filename)

    def build_aliases(self, filename: str) -> tuple[str, ...]:
        return _build_alias_set(filename)

    def is_compatible(self, filename: str, document: Document) -> bool:
        return PlxNamingStrategy().is_compatible(filename, document)

    def find_match(self, filename: str, candidates: list[Document]) -> NameMatchResult:
        return PlxNamingStrategy().find_match(filename, candidates)


class NamingStrategyRegistry:
    def __init__(self, strategies: list) -> None:
        self._strategies = strategies

    def resolve(self, document_type: DocumentType):
        for strategy in self._strategies:
            if strategy.supports(document_type):
                return strategy
        raise LookupError(f'No naming strategy for document type: {document_type}')
