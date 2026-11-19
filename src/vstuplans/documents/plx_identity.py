"""Сопоставление загружаемого PLX с существующими документами."""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from uuid import UUID

from .entities import Document, DocumentVersion


# Поля, сравниваемые строго (равенство).
_STRICT_FIELDS = ('direction_code', 'year_start')

# Аббревиатуры: допускаем правку до MAX_ABBR_EDIT символов.
_ABBR_FIELDS = ('faculty_abbr_en', 'department_abbr_en', 'profile_abbr_en')
_ABBR_FALLBACK = {
    'faculty_abbr_en': 'faculty',
    'department_abbr_en': 'department',
    'profile_abbr_en': 'profile',
}
MAX_ABBR_EDIT = 2


@dataclass(frozen=True)
class MatchSuggestion:
    document_id: UUID
    canonical_name: str
    score: float
    reason: str  # filename_exact | canonical_exact | metadata_approx
    aliases: tuple[str, ...] = ()
    meta_summary: str = ''

    @property
    def score_percent(self) -> int:
        return max(0, min(100, int(round(self.score * 100))))


@dataclass(frozen=True)
class MatchContext:
    suggestions: list[MatchSuggestion]
    incoming_metadata: dict[str, Any]

    @property
    def incoming_canonical_filename(self) -> str:
        value = self.incoming_metadata.get('canonical_filename') or ''
        return value if isinstance(value, str) else ''


def _norm_name(name: str) -> str:
    return Path(name or '').name.lower().strip()


def _norm_token(value: Any) -> str:
    if value is None:
        return ''
    return str(value).strip().lower()


def _abbr_value(meta: dict[str, Any], field: str) -> str:
    raw = meta.get(field) or meta.get(_ABBR_FALLBACK.get(field, ''), '') or ''
    return _norm_token(raw).replace(' ', '')


def _edit_distance(a: str, b: str) -> int:
    """Расстояние Левенштейна (короткие строки)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


def _abbr_similar(a: str, b: str) -> bool:
    if not a or not b:
        return not a and not b
    if a == b:
        return True
    return _edit_distance(a, b) <= MAX_ABBR_EDIT


def _text_similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _meta_summary(meta: dict[str, Any]) -> str:
    parts = [
        meta.get('direction_code') or '',
        meta.get('profile_abbr_en') or meta.get('profile') or '',
        meta.get('faculty_abbr_ru') or meta.get('faculty_abbr_en') or '',
        meta.get('department_abbr_ru') or meta.get('department_abbr_en') or '',
        str(meta.get('year_start') or ''),
    ]
    return ' · '.join(p for p in parts if p)


def _candidate_names(document: Document, version: DocumentVersion | None) -> list[str]:
    names = [_norm_name(document.identity.canonical_name)]
    names.extend(_norm_name(a) for a in document.identity.aliases)
    if version:
        meta = version.extracted_metadata or {}
        names.append(_norm_name(meta.get('canonical_filename') or ''))
        names.append(_norm_name(version.source_filename or ''))
    return [n for n in names if n]


def _metadata_match_score(incoming: dict[str, Any], existing: dict[str, Any]) -> float | None:
    """None — не подходит; иначе score в (0, 1)."""
    for field in _STRICT_FIELDS:
        a = _norm_token(incoming.get(field))
        b = _norm_token(existing.get(field))
        if not a or not b or a != b:
            return None

    abbr_scores: list[float] = []
    for field in _ABBR_FIELDS:
        a = _abbr_value(incoming, field)
        b = _abbr_value(existing, field)
        if not a and not b:
            continue
        if not a or not b:
            return None
        if not _abbr_similar(a, b):
            return None
        abbr_scores.append(_text_similarity(a, b))

    if not abbr_scores:
        # Только строгие поля совпали, аббр. пусты — слабый кандидат.
        return 0.55

    return 0.55 + 0.4 * (sum(abbr_scores) / len(abbr_scores))


def find_plx_suggestions(
    *,
    source_filename: str,
    incoming_meta: dict[str, Any],
    documents: list[Document],
    versions_by_doc: dict[UUID, DocumentVersion | None],
    limit: int = 8,
) -> list[MatchSuggestion]:
    """
    Порядок приоритета:
    1) точное совпадение имени файла / алиаса
    2) точное совпадение канонического имени из метаданных
    3) приближение по метаданным (строгие поля + аббр. с допуском 1–2 символа)
    """
    src_norm = _norm_name(source_filename)
    canon_norm = _norm_name(incoming_meta.get('canonical_filename') or '')

    exact_file: list[MatchSuggestion] = []
    exact_canon: list[MatchSuggestion] = []
    approx: list[MatchSuggestion] = []

    for document in documents:
        version = versions_by_doc.get(document.id)
        names = _candidate_names(document, version)
        existing_meta = (version.extracted_metadata if version else {}) or {}
        summary = _meta_summary(existing_meta) or document.identity.canonical_name

        if src_norm and src_norm in names:
            exact_file.append(
                MatchSuggestion(
                    document_id=document.id,
                    canonical_name=document.identity.canonical_name,
                    score=1.0,
                    reason='filename_exact',
                    aliases=document.identity.aliases,
                    meta_summary=summary,
                )
            )
            continue

        if canon_norm and canon_norm in names:
            exact_canon.append(
                MatchSuggestion(
                    document_id=document.id,
                    canonical_name=document.identity.canonical_name,
                    score=0.95,
                    reason='canonical_exact',
                    aliases=document.identity.aliases,
                    meta_summary=summary,
                )
            )
            continue

        score = _metadata_match_score(incoming_meta, existing_meta)
        if score is None:
            # Также сравним канонические имена как текст (для старых записей без meta).
            existing_canon = _norm_name(
                existing_meta.get('canonical_filename') or document.identity.canonical_name
            )
            if canon_norm and existing_canon:
                sim = _text_similarity(canon_norm, existing_canon)
                if sim >= 0.88:
                    score = 0.5 + 0.4 * sim
                else:
                    continue
            else:
                continue

        approx.append(
            MatchSuggestion(
                document_id=document.id,
                canonical_name=document.identity.canonical_name,
                score=score,
                reason='metadata_approx',
                aliases=document.identity.aliases,
                meta_summary=summary,
            )
        )

    # Точные — сначала; приближённые — по убыванию текстовой близости.
    approx.sort(key=lambda s: (-s.score, s.canonical_name.lower()))
    result = exact_file + exact_canon + approx
    return result[:limit]
