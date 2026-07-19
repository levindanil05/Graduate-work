"""Unit-тесты сопоставления PLX по имени и метаданным."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'src'))
sys.path.insert(0, str(REPO_ROOT / 'src' / 'education_site'))

from documents.entities import (  # noqa: E402
    Document,
    DocumentIdentity,
    DocumentType,
    DocumentVersion,
    VersionStatus,
)
from documents.plx_identity import _abbr_similar, _edit_distance, find_plx_suggestions  # noqa: E402


def _doc(name: str, aliases: tuple[str, ...] = ()) -> Document:
    return Document(
        id=uuid4(),
        document_type=DocumentType.PLX,
        identity=DocumentIdentity(canonical_name=name, aliases=aliases),
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def _ver(document_id, meta: dict, source: str = 'x.plx') -> DocumentVersion:
    return DocumentVersion(
        id=uuid4(),
        document_id=document_id,
        status=VersionStatus.NEW,
        version_number=1,
        source_filename=source,
        storage_key=source,
        content_hash='h',
        extracted_metadata=meta,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


class TestPlxIdentity(unittest.TestCase):
    def test_edit_distance_and_abbr_tolerance(self):
        self.assertEqual(_edit_distance('fast', 'fasst'), 1)
        self.assertTrue(_abbr_similar('FASTIV', 'FASTiV'))
        self.assertTrue(_abbr_similar('PiAS', 'PiA'))
        self.assertFalse(_abbr_similar('AAA', 'ZZZ'))

    def test_filename_exact_preferred(self):
        doc = _doc('plan-a.plx', aliases=('old_name.plx',))
        ver = _ver(doc.id, {'direction_code': '08.03.01', 'year_start': 2024})
        suggestions = find_plx_suggestions(
            source_filename='old_name.plx',
            incoming_meta={
                'direction_code': '08.03.01',
                'year_start': 2024,
                'canonical_filename': 'Ucheb_plan_08.03.01_A_x_O_NOR_f_d_2024.plx',
            },
            documents=[doc],
            versions_by_doc={doc.id: ver},
        )
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].reason, 'filename_exact')
        self.assertEqual(suggestions[0].score, 1.0)

    def test_canonical_exact_when_filename_differs(self):
        canon = 'Ucheb_plan_08.03.01_A_prof_O_NOR_fac_dept_2024.plx'
        doc = _doc(canon)
        ver = _ver(doc.id, {'canonical_filename': canon, 'direction_code': '08.03.01', 'year_start': 2024})
        suggestions = find_plx_suggestions(
            source_filename='random_upload.plx',
            incoming_meta={
                'canonical_filename': canon,
                'direction_code': '08.03.01',
                'year_start': 2024,
            },
            documents=[doc],
            versions_by_doc={doc.id: ver},
        )
        self.assertEqual(suggestions[0].reason, 'canonical_exact')

    def test_metadata_approx_ranks_by_similarity(self):
        base = {
            'direction_code': '08.03.01',
            'year_start': 2024,
            'faculty_abbr_en': 'FASTIV',
            'department_abbr_en': 'PiAS',
            'profile_abbr_en': 'PGS',
        }
        close = _doc('close.plx')
        far = _doc('far.plx')
        close_ver = _ver(close.id, {**base, 'faculty_abbr_en': 'FASTV'})
        far_ver = _ver(far.id, {**base, 'faculty_abbr_en': 'FASTiV', 'department_abbr_en': 'PiA'})
        suggestions = find_plx_suggestions(
            source_filename='new.plx',
            incoming_meta={**base, 'canonical_filename': 'Ucheb_plan_other.plx'},
            documents=[far, close],
            versions_by_doc={close.id: close_ver, far.id: far_ver},
        )
        self.assertEqual(len(suggestions), 2)
        self.assertTrue(all(s.reason == 'metadata_approx' for s in suggestions))
        self.assertGreaterEqual(suggestions[0].score, suggestions[1].score)

    def test_strict_year_blocks_match(self):
        doc = _doc('x.plx')
        ver = _ver(
            doc.id,
            {
                'direction_code': '08.03.01',
                'year_start': 2023,
                'faculty_abbr_en': 'FASTIV',
                'department_abbr_en': 'PiAS',
                'profile_abbr_en': 'PGS',
            },
        )
        suggestions = find_plx_suggestions(
            source_filename='new.plx',
            incoming_meta={
                'direction_code': '08.03.01',
                'year_start': 2024,
                'faculty_abbr_en': 'FASTIV',
                'department_abbr_en': 'PiAS',
                'profile_abbr_en': 'PGS',
                'canonical_filename': 'other.plx',
            },
            documents=[doc],
            versions_by_doc={doc.id: ver},
        )
        self.assertEqual(suggestions, [])


if __name__ == '__main__':
    unittest.main()
