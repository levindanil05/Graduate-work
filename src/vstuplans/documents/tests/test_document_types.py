from __future__ import annotations

import os
import tempfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from accounts.roles import Role
from documents.document_types import (
    build_metadata_extractor,
    get_spec,
    is_known,
    label_for,
    list_specs,
)
from documents.entities import VersionStatus
from documents.factory import build_document_service
from documents.models import Document, DocumentVersion
from documents.services import DomainValidationError, UploadRequest


User = get_user_model()

MEMO_TYPE = {
    'code': 'memo',
    'label': 'Служебная записка',
    'file_extensions': ['.txt'],
    'naming_strategy': 'filename',
    'metadata_extractor': None,
}


class DocumentTypeRegistryTests(TestCase):
    def test_default_registry_keeps_plx_and_generic(self):
        codes = [spec.code for spec in list_specs()]
        self.assertEqual(codes, ['plx', 'printed_form', 'generic'])
        self.assertEqual(get_spec('plx').naming_strategy, 'plx')
        self.assertEqual(get_spec('plx').metadata_extractor, 'plx')
        self.assertEqual(len(get_spec('plx').companions), 1)
        self.assertEqual(get_spec('plx').companions[0].code, 'printed_form')
        self.assertEqual(get_spec('printed_form').file_extensions, ('.pdf', '.xlsx'))
        self.assertIsNotNone(get_spec('printed_form').lifecycle)
        self.assertEqual(get_spec('generic').naming_strategy, 'filename')
        self.assertIsNone(get_spec('generic').metadata_extractor)
        self.assertEqual(label_for('plx'), 'Учебный план (PLX)')
        self.assertEqual(label_for('printed_form'), 'Печатная форма')

    def test_unknown_type_is_rejected(self):
        self.assertFalse(is_known('memo'))
        service = build_document_service()
        with self.assertRaises(DomainValidationError) as caught:
            service._resolve_naming_strategy('memo')
        self.assertIn('memo', str(caught.exception))

    def test_model_rejects_unknown_type(self):
        document = Document(canonical_name='x', document_type='no-such-type')
        with self.assertRaises(ValidationError):
            document.full_clean()

    def test_configured_kind_uploads_without_extractor(self):
        for role in Role:
            Group.objects.get_or_create(name=role.value)
        user = User.objects.create_user(username='uploader', password='x')
        user.groups.add(Group.objects.get(name=Role.ADMINISTRATOR.value))

        fd, name = tempfile.mkstemp(suffix='.txt')
        os.write(fd, b'memo body')
        os.close(fd)
        path = Path(name)
        configured = [*settings.DOCUMENT_TYPES, MEMO_TYPE]
        try:
            with override_settings(DOCUMENT_TYPES=configured):
                self.assertTrue(is_known('memo'))
                self.assertIsNone(build_metadata_extractor('memo'))
                service = build_document_service()
                result = service.upload_new_document(
                    UploadRequest(
                        user_id=user.id,
                        document_type='memo',
                        file_path=path,
                        source_filename='Memo.TXT',
                    )
                )
                document = Document.objects.get(pk=result.document_id)
                version = DocumentVersion.objects.get(pk=result.version_id)
                self.assertEqual(document.document_type, 'memo')
                self.assertEqual(document.get_document_type_display(), 'Служебная записка')
                self.assertEqual(document.canonical_name, 'memo.txt')
                self.assertEqual(version.status, VersionStatus.NEW.value)
                self.assertEqual(version.extracted_metadata, {})
        finally:
            path.unlink(missing_ok=True)
