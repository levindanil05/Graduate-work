from __future__ import annotations

from pathlib import Path
from typing import Any

from documents.entities import DocumentType

QUALIFICATION_MAP = {
    '1': 'Бакалавриат',
    '2': 'Магистратура',
    '3': 'Специалитет',
}


def normalize_qualification(value: str) -> str:
    if value and str(value).strip() in QUALIFICATION_MAP:
        return QUALIFICATION_MAP[str(value).strip()]
    return value or ''


class PlxMetadataExtractor:
    def supports(self, document_type: DocumentType) -> bool:
        return document_type == DocumentType.PLX

    def extract(self, file_path: Path) -> dict[str, Any]:
        from plx_parser import parse_plx_file
        from plans.canonical_name import build_canonical_name, enrich_meta_with_abbrs

        data = parse_plx_file(str(file_path))
        if data.get('error'):
            raise ValueError(data['error'])

        year_str = data.get('year_start', '')
        year = int(year_str) if year_str and str(year_str).isdigit() else None
        profiles = data.get('profiles') or []
        enriched = enrich_meta_with_abbrs(data)

        return {
            'direction_code': enriched.get('direction_code', ''),
            'direction': enriched.get('direction', ''),
            'faculty': enriched.get('faculty', ''),
            'department': enriched.get('department', ''),
            'year_start': year,
            'qualification': normalize_qualification(enriched.get('qualification', '')),
            'profiles': profiles,
            'profile': enriched.get('profile') or (profiles[0] if profiles else ''),
            'study_form_en': enriched.get('study_form_en', ''),
            'study_form': enriched.get('study_form', ''),
            'program_kind': enriched.get('program_kind', ''),
            'term_code': enriched.get('term_code', ''),
            'education_level': enriched.get('education_level', ''),
            'education_plan_kind': enriched.get('education_plan_kind', ''),
            'faculty_abbr_en': enriched.get('faculty_abbr_en', ''),
            'faculty_abbr_ru': enriched.get('faculty_abbr_ru', ''),
            'department_abbr_en': enriched.get('department_abbr_en', ''),
            'department_abbr_ru': enriched.get('department_abbr_ru', ''),
            'profile_abbr_en': enriched.get('profile_abbr_en', ''),
            'profile_abbr_ru': enriched.get('profile_abbr_ru', ''),
            'canonical_filename': build_canonical_name(enriched),
        }
