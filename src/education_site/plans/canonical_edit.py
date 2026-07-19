"""Проверка каноничности имени PLX и правка через поля метаданных."""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from django.utils.translation import gettext_lazy as _

from plans.canonical_name import build_canonical_name

# Поля, из которых собирается каноническое имя (порядок = токены после Ucheb_plan).
NAME_TOKEN_FIELDS: tuple[str, ...] = (
    'direction_code',
    'program_kind',
    'profile_abbr_en',
    'study_form_en',
    'term_code',
    'faculty_abbr_en',
    'department_abbr_en',
    'year_start',
)

PROGRAM_KIND_CHOICES = ('A', 'P', '-')
STUDY_FORM_CHOICES = ('O', 'Z', 'V')
TERM_CODE_CHOICES = ('NOR', 'SOKR', '2VO')

# Сколько токенов имени можно изменить относительно авто-имени без «сильного отклонения».
MAX_TOKEN_DIFFS = 3
MIN_NAME_SIMILARITY = 0.70

_DIRECTION_RE = re.compile(r'^\d{2}\.\d{2}\.\d{2}$')
_ABBR_RE = re.compile(r'^[A-Za-z0-9-]{1,32}$')
_YEAR_RE = re.compile(r'^\d{4}$')

FIELD_LABELS: dict[str, Any] = {
    'direction_code': _('Direction code'),
    'program_kind': _('Program kind (A/P/-)'),
    'profile_abbr_en': _('Profile abbreviation (Latin)'),
    'study_form_en': _('Study form (O/Z/V)'),
    'term_code': _('Term code'),
    'faculty_abbr_en': _('Faculty abbreviation (Latin)'),
    'department_abbr_en': _('Department abbreviation (Latin)'),
    'year_start': _('Admission year'),
}


@dataclass(frozen=True)
class NamingFieldSpec:
    key: str
    label: Any
    choices: tuple[str, ...] | None = None


NAMING_FIELD_SPECS: tuple[NamingFieldSpec, ...] = (
    NamingFieldSpec('direction_code', FIELD_LABELS['direction_code']),
    NamingFieldSpec('program_kind', FIELD_LABELS['program_kind'], PROGRAM_KIND_CHOICES),
    NamingFieldSpec('profile_abbr_en', FIELD_LABELS['profile_abbr_en']),
    NamingFieldSpec('study_form_en', FIELD_LABELS['study_form_en'], STUDY_FORM_CHOICES),
    NamingFieldSpec('term_code', FIELD_LABELS['term_code'], TERM_CODE_CHOICES),
    NamingFieldSpec('faculty_abbr_en', FIELD_LABELS['faculty_abbr_en']),
    NamingFieldSpec('department_abbr_en', FIELD_LABELS['department_abbr_en']),
    NamingFieldSpec('year_start', FIELD_LABELS['year_start']),
)


@dataclass(frozen=True)
class CanonicityStatus:
    is_canonical: bool
    current_filename: str
    document_canonical_name: str
    expected_canonical: str
    auto_canonical: str
    source_differs: bool
    document_differs: bool


def normalize_filename(name: str) -> str:
    return Path(name or '').name.strip().lower()


def auto_canonical_from_meta(meta: dict[str, Any]) -> str:
    stored = meta.get('canonical_filename_auto')
    if isinstance(stored, str) and stored.strip():
        return stored.strip()
    return build_canonical_name(meta)


def expected_canonical_from_meta(meta: dict[str, Any]) -> str:
    stored = meta.get('canonical_filename')
    if isinstance(stored, str) and stored.strip():
        return stored.strip()
    return auto_canonical_from_meta(meta)


def check_canonicity(
    *,
    source_filename: str,
    document_canonical_name: str,
    meta: dict[str, Any],
) -> CanonicityStatus:
    expected = expected_canonical_from_meta(meta)
    auto = auto_canonical_from_meta(meta)
    src_norm = normalize_filename(source_filename)
    doc_norm = normalize_filename(document_canonical_name)
    exp_norm = normalize_filename(expected)
    source_differs = bool(src_norm and exp_norm and src_norm != exp_norm)
    document_differs = bool(doc_norm and exp_norm and doc_norm != exp_norm)
    return CanonicityStatus(
        is_canonical=not source_differs and not document_differs,
        current_filename=Path(source_filename or '').name,
        document_canonical_name=document_canonical_name,
        expected_canonical=expected,
        auto_canonical=auto,
        source_differs=source_differs,
        document_differs=document_differs,
    )


def naming_values_from_meta(meta: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in NAME_TOKEN_FIELDS:
        raw = meta.get(key, '')
        values[key] = '' if raw is None else str(raw).strip()
    if not values.get('program_kind'):
        values['program_kind'] = 'A'
    return values


def parse_naming_post(post_data) -> dict[str, str]:
    values: dict[str, str] = {}
    for key in NAME_TOKEN_FIELDS:
        values[key] = (post_data.get(key) or '').strip()
    return values


def validate_naming_fields(values: dict[str, str]) -> list[str]:
    errors: list[str] = []
    code = values.get('direction_code', '')
    if not _DIRECTION_RE.match(code):
        errors.append(str(_('Direction code must look like 08.03.01')))

    kind = values.get('program_kind', '')
    if kind not in PROGRAM_KIND_CHOICES:
        errors.append(str(_('Program kind must be A, P or -')))

    form = values.get('study_form_en', '')
    if form not in STUDY_FORM_CHOICES:
        errors.append(str(_('Study form must be O, Z or V')))

    term = values.get('term_code', '')
    if term not in TERM_CODE_CHOICES:
        errors.append(str(_('Term code must be NOR, SOKR or 2VO')))

    year = values.get('year_start', '')
    if not _YEAR_RE.match(year):
        errors.append(str(_('Admission year must be a 4-digit number')))

    for key in ('profile_abbr_en', 'faculty_abbr_en', 'department_abbr_en'):
        abbr = values.get(key, '')
        if not _ABBR_RE.match(abbr):
            errors.append(
                str(
                    _('Abbreviation «%(field)s» must be Latin letters/digits (1–32)')
                    % {'field': str(FIELD_LABELS[key])}
                )
            )
    return errors


def build_name_from_naming_values(values: dict[str, str]) -> str:
    """Собирает имя строго из пользовательских токенов (без словаря аббревиатур)."""
    kind = (values.get('program_kind') or 'A').strip() or 'A'
    parts = [
        'Ucheb_plan',
        (values.get('direction_code') or '').strip(),
        kind,
        (values.get('profile_abbr_en') or '').strip(),
        (values.get('study_form_en') or '').strip(),
        (values.get('term_code') or '').strip(),
        (values.get('faculty_abbr_en') or '').strip(),
        (values.get('department_abbr_en') or '').strip(),
        str(values.get('year_start') or '').strip(),
    ]
    return '_'.join(parts) + '.plx'


def apply_naming_values(meta: dict[str, Any], values: dict[str, str]) -> dict[str, Any]:
    out = dict(meta)
    for key, value in values.items():
        if key == 'year_start' and value.isdigit():
            out[key] = int(value)
        else:
            out[key] = value
    # Пользователь задал en-токены явно — не перетираем их через словарь.
    out['canonical_filename'] = build_name_from_naming_values(values)
    if not out.get('canonical_filename_auto'):
        out['canonical_filename_auto'] = auto_canonical_from_meta(meta) or out['canonical_filename']
    return out


def name_tokens(filename: str) -> list[str]:
    stem = Path(filename).stem
    parts = stem.split('_')
    # Ucheb_plan_... → ['Ucheb', 'plan', ...]
    if len(parts) >= 2 and parts[0].lower() == 'ucheb' and parts[1].lower() == 'plan':
        return parts[2:]
    return parts


def deviation_ok(auto_name: str, proposed_name: str) -> bool:
    """Имя не должно сильно уезжать от автоматически вычисленного."""
    if normalize_filename(auto_name) == normalize_filename(proposed_name):
        return True
    a_tokens = name_tokens(auto_name)
    b_tokens = name_tokens(proposed_name)
    if len(a_tokens) == len(b_tokens) == len(NAME_TOKEN_FIELDS):
        diffs = sum(1 for a, b in zip(a_tokens, b_tokens) if a.lower() != b.lower())
        if diffs <= MAX_TOKEN_DIFFS:
            return True
    ratio = SequenceMatcher(
        None,
        normalize_filename(auto_name),
        normalize_filename(proposed_name),
    ).ratio()
    return ratio >= MIN_NAME_SIMILARITY


def build_preview_name(values: dict[str, str]) -> str:
    return build_name_from_naming_values(values)
