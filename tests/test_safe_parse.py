"""Проверка, что разбор PLX находит plx_parser (в т.ч. рядом с Django-проектом)."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'src' / 'vstuplans'))

from documents.infra.safe_parse import parse_plx_with_timeout  # noqa: E402

_MINIMAL_PLX = """<?xml version="1.0" encoding="utf-8"?>
<MMISDB xmlns="http://tempuri.org/dsMMISDB.xsd">
  <ООП Шифр="09.03.01" Название="Информатика и вычислительная техника" Квалификация="бакалавр" ПрограммаПодготовки="3"/>
  <Планы
    ГодНачалаПодготовки="2020"
    КодПрофКафедры="47"
    КодФакультета="-1"
    КодФормыОбучения="1"
    КодПрограммы="3"
    КодУровняОбразования="3"
    СрокОбучения="4"
    Титул="Профиль «Вычислительные машины»"
  />
</MMISDB>
"""


def test_parse_plx_with_timeout_finds_parser():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'sample.plx'
        path.write_text(_MINIMAL_PLX, encoding='utf-8')
        result = parse_plx_with_timeout(path, timeout_seconds=15)

    err = str(result.get('error') or '')
    assert "No module named 'plx_parser'" not in err, result
    assert "No module named" not in err, result
    assert not err, result
    assert result.get('direction_code') == '09.03.01'
