from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.roles import Role
from documents.entities import DocumentType, VersionStatus
from documents.factory import build_document_service
from documents.infra.storage import LocalStoragePort
from documents.models import DocumentVersion, StorageShareLink
from documents.services import UploadRequest
from documents.tests.fake_nextcloud import build_fake_nextcloud_port


User = get_user_model()


class NextcloudDownloadAndLifecycleTests(TestCase):
    _sample = (
        Path(__file__).resolve().parents[4]
        / 'tests'
        / 'test_data'
        / 'sample1_full.plx'
    )

    def setUp(self):
        for role in Role:
            Group.objects.get_or_create(name=role.value)
        self.user = User.objects.create_user(username='nc_user', password='x')
        self.user.groups.add(Group.objects.get(name=Role.ADMINISTRATOR.value))
        self._tmpdir = tempfile.TemporaryDirectory()
        self.storage, self.session = build_fake_nextcloud_port(Path(self._tmpdir.name))
        self.client = Client()
        self.client.force_login(self.user)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _copy_sample(self) -> Path:
        fd, name = tempfile.mkstemp(suffix='.plx')
        import os

        os.close(fd)
        tmp = Path(name)
        shutil.copy2(self._sample, tmp)
        return tmp

    def test_page_puts_direct_link_without_get(self):
        path = self._copy_sample()
        try:
            with patch('documents.factory.build_storage_port', return_value=self.storage):
                with patch('plans.document_views.build_storage_port', return_value=self.storage):
                    service = build_document_service()
                    result = service.upload_new_document(
                        UploadRequest(
                            user_id=self.user.id,
                            document_type=DocumentType.PLX,
                            file_path=path,
                            source_filename='plan.plx',
                        )
                    )
                    before_gets = self.session.get_count
                    response = self.client.get(
                        reverse('plans:document_detail', args=[result.document_id])
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(self.session.get_count, before_gets)
                    self.assertContains(response, '/s/')
                    self.assertContains(response, '/download/')
        finally:
            path.unlink(missing_ok=True)

    def test_download_redirects_to_share(self):
        path = self._copy_sample()
        try:
            with patch('documents.factory.build_storage_port', return_value=self.storage):
                with patch('plans.document_views.build_storage_port', return_value=self.storage):
                    service = build_document_service()
                    result = service.upload_new_document(
                        UploadRequest(
                            user_id=self.user.id,
                            document_type=DocumentType.PLX,
                            file_path=path,
                            source_filename='plan.plx',
                        )
                    )
                    response = self.client.get(
                        reverse('plans:download_current', args=[result.document_id])
                    )
                    self.assertEqual(response.status_code, 302)
                    self.assertIn('/s/', response['Location'])
                    self.assertEqual(response.get('Cache-Control'), 'no-store')
        finally:
            path.unlink(missing_ok=True)

    def test_share_failure_falls_back_to_stream(self):
        path = self._copy_sample()
        self.session.fail_share = True
        try:
            with patch('documents.factory.build_storage_port', return_value=self.storage):
                with patch('plans.document_views.build_storage_port', return_value=self.storage):
                    service = build_document_service()
                    result = service.upload_new_document(
                        UploadRequest(
                            user_id=self.user.id,
                            document_type=DocumentType.PLX,
                            file_path=path,
                            source_filename='plan.plx',
                        )
                    )
                    response = self.client.get(
                        reverse('plans:download_current', args=[result.document_id])
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertTrue(response.get('Content-Disposition', '').startswith('attachment'))
        finally:
            path.unlink(missing_ok=True)

    def test_trash_revokes_shares(self):
        path = self._copy_sample()
        try:
            with patch('documents.factory.build_storage_port', return_value=self.storage):
                service = build_document_service()
                result = service.upload_new_document(
                    UploadRequest(
                        user_id=self.user.id,
                        document_type=DocumentType.PLX,
                        file_path=path,
                        source_filename='plan.plx',
                    )
                )
                version = DocumentVersion.objects.get(pk=result.version_id)
                self.storage.direct_download_url(version.storage_key, version.source_filename)
                self.assertTrue(StorageShareLink.objects.filter(storage_key=version.storage_key).exists())
                service.transition_version_status(
                    version_id=version.id,
                    actor_user_id=self.user.id,
                    target_status=VersionStatus.TRASHED,
                    action_comment='',
                    allow_without_comment=True,
                )
                self.assertFalse(
                    StorageShareLink.objects.filter(storage_key=version.storage_key).exists()
                )
        finally:
            path.unlink(missing_ok=True)


@override_settings(STORAGE_BACKEND='local')
class MigrateStorageBackendTests(TestCase):
    def setUp(self):
        self._local_tmp = tempfile.TemporaryDirectory()
        self._nc_tmp = tempfile.TemporaryDirectory()
        self.local = LocalStoragePort(root=Path(self._local_tmp.name))
        self.nc, self.session = build_fake_nextcloud_port(Path(self._nc_tmp.name))

    def tearDown(self):
        self._local_tmp.cleanup()
        self._nc_tmp.cleanup()

    def test_migrate_and_idempotent(self):
        from django.core.management import call_command
        from io import StringIO

        from documents.models import Document

        src = Path(self._local_tmp.name) / 'src.plx'
        src.write_bytes(b'payload')
        key = self.local.save(src, 'documents/d1/v1.plx')
        doc = Document.objects.create(document_type='generic', canonical_name='plan.plx')
        DocumentVersion.objects.create(
            document=doc,
            version_number=1,
            status='new',
            source_filename='plan.plx',
            storage_key=key,
            content_hash='abc',
        )

        def build(name):
            return self.local if name == 'local' else self.nc

        out = StringIO()
        with patch(
            'documents.management.commands.migrate_storage_backend.Command._build',
            side_effect=build,
        ):
            call_command(
                'migrate_storage_backend',
                '--from',
                'local',
                '--to',
                'nextcloud',
                '--verify',
                stdout=out,
            )
            self.assertTrue(self.nc.exists(key))
            call_command(
                'migrate_storage_backend',
                '--from',
                'local',
                '--to',
                'nextcloud',
                stdout=out,
            )
        self.assertIn('пропущено 1', out.getvalue())

    def test_dry_run_does_not_copy(self):
        from django.core.management import call_command
        from io import StringIO

        from documents.models import Document

        src = Path(self._local_tmp.name) / 'src.plx'
        src.write_bytes(b'x')
        key = self.local.save(src, 'documents/d1/v2.plx')
        doc = Document.objects.create(document_type='generic', canonical_name='p.plx')
        DocumentVersion.objects.create(
            document=doc,
            version_number=1,
            status='new',
            source_filename='p.plx',
            storage_key=key,
            content_hash='x',
        )

        def build(name):
            return self.local if name == 'local' else self.nc

        out = StringIO()
        with patch(
            'documents.management.commands.migrate_storage_backend.Command._build',
            side_effect=build,
        ):
            call_command(
                'migrate_storage_backend',
                '--from',
                'local',
                '--to',
                'nextcloud',
                '--dry-run',
                stdout=out,
            )
        self.assertFalse(self.nc.exists(key))
        self.assertIn('dry-run', out.getvalue())
