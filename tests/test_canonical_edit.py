"""Тесты проверки каноничности и правки имени через поля метаданных."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'src'))
sys.path.insert(0, str(REPO_ROOT / 'src' / 'education_site'))

# gettext_lazy нужен Django settings — подставляем простую заглушку до импорта.
import django
from django.conf import settings

if not settings.configured:
    settings.configure(
        USE_I18N=True,
        LANGUAGE_CODE='en',
        SECRET_KEY='test',
    )
    django.setup()

from plans.canonical_edit import (  # noqa: E402
    apply_naming_values,
    build_name_from_naming_values,
    build_preview_name,
    check_canonicity,
    deviation_ok,
    name_tokens,
    validate_naming_fields,
)


class TestCanonicalEdit(unittest.TestCase):
    def test_build_name_from_values(self):
        name = build_name_from_naming_values(
            {
                'direction_code': '08.03.01',
                'program_kind': 'A',
                'profile_abbr_en': 'PGS',
                'study_form_en': 'O',
                'term_code': 'NOR',
                'faculty_abbr_en': 'FASTIV',
                'department_abbr_en': 'PiAS',
                'year_start': '2024',
            }
        )
        self.assertEqual(
            name,
            'Ucheb_plan_08.03.01_A_PGS_O_NOR_FASTIV_PiAS_2024.plx',
        )

    def test_validate_rejects_bad_code(self):
        errors = validate_naming_fields(
            {
                'direction_code': 'bad',
                'program_kind': 'A',
                'profile_abbr_en': 'PGS',
                'study_form_en': 'O',
                'term_code': 'NOR',
                'faculty_abbr_en': 'FASTIV',
                'department_abbr_en': 'PiAS',
                'year_start': '2024',
            }
        )
        self.assertTrue(errors)

    def test_canonicity_detects_mismatch(self):
        meta = {
            'canonical_filename': 'Ucheb_plan_08.03.01_A_PGS_O_NOR_FASTIV_PiAS_2024.plx',
            'canonical_filename_auto': 'Ucheb_plan_08.03.01_A_PGS_O_NOR_FASTIV_PiAS_2024.plx',
        }
        status = check_canonicity(
            source_filename='новый_2.plx',
            document_canonical_name='новый_2.plx',
            meta=meta,
        )
        self.assertFalse(status.is_canonical)
        self.assertTrue(status.source_differs)

    def test_canonicity_ok_when_names_match(self):
        name = 'Ucheb_plan_08.03.01_A_PGS_O_NOR_FASTIV_PiAS_2024.plx'
        status = check_canonicity(
            source_filename=name,
            document_canonical_name=name,
            meta={'canonical_filename': name, 'canonical_filename_auto': name},
        )
        self.assertTrue(status.is_canonical)

    def test_deviation_allows_few_token_changes(self):
        auto = 'Ucheb_plan_08.03.01_A_PGS_O_NOR_FASTIV_PiAS_2024.plx'
        edited = 'Ucheb_plan_08.03.01_A_PGS_O_NOR_FASTV_PiAS_2024.plx'
        self.assertTrue(deviation_ok(auto, edited))
        far = 'Ucheb_plan_09.03.01_P_XXX_Z_SOKR_AAA_BBB_1999.plx'
        self.assertFalse(deviation_ok(auto, far))

    def test_name_tokens(self):
        tokens = name_tokens('Ucheb_plan_08.03.01_A_PGS_O_NOR_FASTIV_PiAS_2024.plx')
        self.assertEqual(
            tokens,
            ['08.03.01', 'A', 'PGS', 'O', 'NOR', 'FASTIV', 'PiAS', '2024'],
        )

    def test_apply_preserves_auto_name(self):
        meta = {
            'direction_code': '08.03.01',
            'canonical_filename_auto': 'Ucheb_plan_08.03.01_A_PGS_O_NOR_FASTIV_PiAS_2024.plx',
        }
        values = {
            'direction_code': '08.03.01',
            'program_kind': 'A',
            'profile_abbr_en': 'PGS',
            'study_form_en': 'O',
            'term_code': 'NOR',
            'faculty_abbr_en': 'FASTV',
            'department_abbr_en': 'PiAS',
            'year_start': '2024',
        }
        out = apply_naming_values(meta, values)
        self.assertEqual(out['canonical_filename'], build_preview_name(values))
        self.assertEqual(out['canonical_filename_auto'], meta['canonical_filename_auto'])


if __name__ == '__main__':
    unittest.main()
