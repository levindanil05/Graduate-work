from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import TestCase

from documents.entities import VersionStatus
from documents.models import DocumentVersion
from external_sync.models import (
    ExternalConnection,
    ExternalSyncSettings,
    RemoteObjectSnapshot,
    WriteMode,
)
from external_sync.providers.fake import FakeProvider
from external_sync.services.reconcile import ReconciliationService


class FakeReconcileTests(TestCase):
    def setUp(self):
        ExternalSyncSettings.objects.update_or_create(pk=1, defaults={'external_sync_enabled': True})
        self.connection = ExternalConnection.objects.create(
            slug='fake_conn',
            name='Fake',
            provider_key='fake',
            credential_ref='NONE',
            write_mode=WriteMode.READ_ONLY,
            enabled=True,
            pull_enabled=True,
            manual_run_enabled=True,
        )
        self.provider = FakeProvider(read_only=True, root='/')
        self.provider.seed_file('/active/plan.plx', b'approved-bytes', md5='md5-a')
        self.provider.seed_file('/active/Архив/old.plx', b'archived-bytes', md5='md5-b')

    def test_second_run_imports_nothing(self):
        service = ReconciliationService(self.connection, provider=self.provider)
        first = service.run()
        self.assertEqual(first.imported_count, 2)

        service2 = ReconciliationService(self.connection, provider=self.provider)
        second = service2.run()
        self.assertEqual(second.imported_count, 0)
        self.assertGreaterEqual(second.skipped_count, 2)

    def test_trusted_import_sets_approved_and_archived(self):
        service = ReconciliationService(self.connection, provider=self.provider)
        service.run()
        approved = DocumentVersion.objects.filter(status=VersionStatus.APPROVED.value)
        archived = DocumentVersion.objects.filter(status=VersionStatus.ARCHIVED.value)
        self.assertEqual(approved.count(), 1)
        self.assertEqual(archived.count(), 1)
        self.assertEqual(RemoteObjectSnapshot.objects.filter(connection=self.connection).count(), 2)

    def test_readonly_blocks_push(self):
        rw = ExternalConnection.objects.create(
            slug='fake_rw',
            name='Fake RW',
            provider_key='fake',
            credential_ref='NONE',
            write_mode=WriteMode.READ_WRITE,
            enabled=True,
            push_enabled=True,
            manual_run_enabled=True,
        )
        provider = FakeProvider(read_only=True)
        service = ReconciliationService(rw, provider=provider)
        run = service.run(push_only=True)
        self.assertIn(run.status, ('completed', 'paused'))
