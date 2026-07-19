"""Реэкспорт парсера PLX (источник истины — src/plx_parser.py)."""
from plx_parser import (  # noqa: F401
    parse_plx_file,
    _decode_xml_bytes,
    _nsmap_from_root,
)
