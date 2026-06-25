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

        data = parse_plx_file(str(file_path))
        if data.get('error'):
            raise ValueError(data['error'])

        year_str = data.get('year_start', '')
        year = int(year_str) if year_str and str(year_str).isdigit() else None
        return {
            'direction_code': data.get('direction_code', ''),
            'direction': data.get('direction', ''),
            'faculty': data.get('faculty', ''),
            'department': data.get('department', ''),
            'year_start': year,
            'qualification': normalize_qualification(data.get('qualification', '')),
        }
