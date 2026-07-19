"""Тесты построения канонического имени PLX (без использования имени файла)."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'src'))
sys.path.insert(0, str(REPO_ROOT / 'src' / 'education_site'))

from plx_parser import parse_plx_file  # noqa: E402
from plans.canonical_name import (  # noqa: E402
    build_canonical_name,
    load_abbr_dict,
    reload_abbr_dict,
    resolve_abbr,
    transliterate_ru,
)


class TestTransliterate(unittest.TestCase):
    def test_fevt_poas(self):
        self.assertEqual(transliterate_ru('ФЭВТ'), 'FEVT')
        self.assertEqual(transliterate_ru('ПОАС'), 'POAS')


class TestCanonicalFromUserfiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reload_abbr_dict()

    def _path(self, *parts: str) -> str:
        path = REPO_ROOT.joinpath(*parts)
        if path.is_file():
            return str(path)
        found = list((REPO_ROOT / 'userfiles').rglob(parts[-1]))
        if found:
            return str(found[0])
        self.skipTest(f'Нет файла: {parts[-1]}')

    def test_rpis_components(self):
        path = self._path('userfiles', 'other', 'Ucheb_plan_09.03.04_A_RPIS_O_NOR_FEVT_POAS_2023.plx')
        meta = parse_plx_file(path)
        self.assertFalse(meta.get('error'), meta.get('error'))
        self.assertEqual(meta['direction_code'], '09.03.04')
        self.assertEqual(meta['study_form_en'], 'O')
        self.assertEqual(meta['term_code'], 'NOR')
        self.assertEqual(meta['year_start'], '2023')
        # Имя файла / ИмяФайла не должны участвовать в program_kind
        kind_without_name = meta['program_kind']
        meta_no_name = dict(meta)
        meta_no_name['source_filename'] = 'Ucheb_plan_00.00.00_P_XXX_Z_SOKR_AAA_BBB_1999.plx'
        built_a = build_canonical_name(meta)
        built_b = build_canonical_name(meta_no_name)
        self.assertEqual(built_a, built_b)
        self.assertEqual(kind_without_name, meta_no_name['program_kind'])
        self.assertIn('_FEVT_', built_a)
        self.assertIn('_POAS_', built_a)
        self.assertIn('_RPIS_', built_a)

    def test_tek2_profile_and_form(self):
        path = self._path('userfiles', 'other', 'Ucheb_plan_09.04.01_A_TEK-2_O_NOR_FEVT_SAPR_2022.plx')
        meta = parse_plx_file(path)
        self.assertFalse(meta.get('error'), meta.get('error'))
        built = build_canonical_name(meta)
        self.assertIn('TEK-2', built)
        self.assertIn('_O_NOR_', built)
        self.assertTrue(built.startswith('Ucheb_plan_09.04.01_'))

    def test_sokr_term(self):
        path = self._path(
            'userfiles', 'ВТФ', 'Ucheb_plan_09.03.01_A_VMKSiS_Z_SOKR_MMF_EVM_2020.plx'
        )
        meta = parse_plx_file(path)
        self.assertEqual(meta['term_code'], 'SOKR')
        self.assertEqual(meta['study_form_en'], 'Z')
        built = build_canonical_name(meta)
        self.assertIn('_SOKR_', built)

    def test_2vo_term(self):
        found = list((REPO_ROOT / 'userfiles').rglob('*_2VO_*.plx'))
        if not found:
            self.skipTest('Нет файлов 2VO в userfiles')
        meta = parse_plx_file(str(found[0]))
        self.assertEqual(meta['term_code'], '2VO')
        self.assertTrue(meta.get('is_shortened'))
        built = build_canonical_name(meta)
        self.assertIn('_2VO_', built)


class TestBuildDoesNotReadFilename(unittest.TestCase):
    def test_source_filename_ignored(self):
        meta = {
            'direction_code': '09.03.04',
            'program_kind': 'A',
            'profile': 'Разработка программно-информационных систем',
            'profile_prefix_raw': '',
            'study_form_en': 'O',
            'term_code': 'NOR',
            'faculty': 'электроники и вычислительной техники',
            'faculty_abbr_raw': '',
            'department': 'Программное обеспечение автоматизированных систем',
            'department_abbr_raw': '',
            'year_start': '2023',
            'source_filename': 'Ucheb_plan_99.99.99_P_HACK_Z_SOKR_XXX_YYY_1999.plx',
        }
        reload_abbr_dict()
        built = build_canonical_name(meta)
        self.assertNotIn('HACK', built)
        self.assertNotIn('99.99.99', built)
        self.assertNotIn('_SOKR_', built)
        self.assertTrue(built.startswith('Ucheb_plan_09.03.04_A_'))
        self.assertIn('_O_NOR_', built)


class TestGroupedFormsDict(unittest.TestCase):
    def test_two_forms_same_en_ru(self):
        import tempfile

        yaml_text = """
faculty:
  - en: FTKM
    ru: ФТКМ
    forms:
      - "технологии конструкционных материалов"
      - "Факультет технологии конструкционных материалов"
department: []
profile: []
"""
        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.yaml',
            delete=False,
            encoding='utf-8',
        ) as fh:
            fh.write(yaml_text)
            path = fh.name
        try:
            data = reload_abbr_dict(path)
            a = resolve_abbr(
                'faculty',
                'технологии конструкционных материалов',
                dict_data=data,
            )
            b = resolve_abbr(
                'faculty',
                'Факультет технологии конструкционных материалов',
                dict_data=data,
            )
            self.assertEqual(a, {'en': 'FTKM', 'ru': 'ФТКМ'})
            self.assertEqual(b, {'en': 'FTKM', 'ru': 'ФТКМ'})
            self.assertEqual(a, b)
        finally:
            Path(path).unlink(missing_ok=True)
            reload_abbr_dict()  # вернуть основной словарь


if __name__ == '__main__':
    unittest.main()
