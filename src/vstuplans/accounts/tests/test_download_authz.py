from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client, TestCase

from accounts.roles import Role
from documents.models import Document, DocumentType, DocumentVersion, VersionStatus


class DownloadAuthzTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.reader = User.objects.create_user('reader1', password='password12345')
        Group.objects.get_or_create(name=Role.READER.value)
        self.reader.groups.add(Group.objects.get(name=Role.READER.value))

        self.doc = Document.objects.create(
            document_type=DocumentType.PLX,
            canonical_name='test_plan.plx',
        )
        self.version = DocumentVersion.objects.create(
            document=self.doc,
            status=VersionStatus.APPROVED,
            version_number=1,
            source_filename='test_plan.plx',
            storage_key='documents/x/y.plx',
            content_hash='abc',
        )
        self.doc.current_version = self.version
        self.doc.save(update_fields=['current_version'])

        self.trashed = DocumentVersion.objects.create(
            document=self.doc,
            status=VersionStatus.TRASHED,
            version_number=2,
            source_filename='old.plx',
            storage_key='documents/x/z.plx',
            content_hash='def',
        )

    def test_reader_can_download_approved(self):
        from accounts.permissions import RolePermissionService

        self.assertTrue(
            RolePermissionService().can_download(self.reader.pk, self.version)
        )

    def test_reader_cannot_download_trashed(self):
        from accounts.permissions import RolePermissionService

        self.assertFalse(
            RolePermissionService().can_download(self.reader.pk, self.trashed)
        )

    def test_anonymous_redirected(self):
        client = Client()
        response = client.get(f'/doc/{self.doc.id}/download/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)
