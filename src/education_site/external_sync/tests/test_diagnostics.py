from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase

from external_sync.models import ExternalConnection, WriteMode
from external_sync.services.diagnostics import run_connection_diagnostics


class DiagnosticsTests(TestCase):
    def setUp(self):
        self.connection = ExternalConnection.objects.create(
            slug='diag_test',
            name='Diag test',
            provider_key='yandex_disk',
            root_path='/plans',
            credential_ref='YANDEX_DISK_UO_READONLY_TOKEN',
            write_mode=WriteMode.READ_ONLY,
            enabled=True,
        )

    def test_missing_token_fails_early(self):
        with patch.dict(
            os.environ,
            {
                'YANDEX_DISK_UO_READONLY_TOKEN': '',
                'YANDEX_DISK_TOKEN': '',
            },
            clear=False,
        ), self.settings(YANDEX_DISK_UO_READONLY_TOKEN='', YANDEX_DISK_TOKEN=''):
            report = run_connection_diagnostics(self.connection, disk=MagicMock())
        by_id = {s.id: s for s in report.steps}
        self.assertEqual(by_id['token_present'].status, 'fail')
        self.assertEqual(by_id['token_valid'].status, 'skip')
        self.assertEqual(by_id['root_exists'].status, 'skip')
        self.assertEqual(report.verdict, 'failed')

    def test_happy_path_readonly_shallow_list(self):
        disk = MagicMock()
        disk.check_token.return_value = True
        disk.exists.return_value = True
        disk.get_meta.return_value = SimpleNamespace(type='dir', path='/plans', name='plans')
        disk.listdir.return_value = [
            SimpleNamespace(type='dir', name='ФТФ', path='/plans/ФТФ'),
            SimpleNamespace(type='file', name='plan.plx', path='/plans/plan.plx'),
            SimpleNamespace(type='file', name='readme.txt', path='/plans/readme.txt'),
        ]

        with self.settings(YANDEX_DISK_UO_READONLY_TOKEN='test-token'):
            report = run_connection_diagnostics(self.connection, disk=disk)

        by_id = {s.id: s for s in report.steps}
        self.assertEqual(by_id['token_present'].status, 'ok')
        self.assertEqual(by_id['token_valid'].status, 'ok')
        self.assertEqual(by_id['root_exists'].status, 'ok')
        self.assertEqual(by_id['root_is_dir'].status, 'ok')
        self.assertEqual(by_id['shallow_list'].status, 'ok')
        self.assertIn('.plx 1', by_id['shallow_list'].detail)
        self.assertEqual(by_id['write_probe'].status, 'skip')
        self.assertEqual(report.verdict, 'ok')
        disk.listdir.assert_called_once()
        kwargs = disk.listdir.call_args.kwargs
        self.assertEqual(kwargs.get('limit'), 30)
        self.assertEqual(kwargs.get('offset'), 0)

    def test_warn_when_only_subdirs(self):
        disk = MagicMock()
        disk.check_token.return_value = True
        disk.exists.return_value = True
        disk.get_meta.return_value = SimpleNamespace(type='dir', path='/plans', name='plans')
        disk.listdir.return_value = [
            SimpleNamespace(type='dir', name='ФТФ', path='/plans/ФТФ'),
        ]

        with self.settings(YANDEX_DISK_UO_READONLY_TOKEN='test-token'):
            report = run_connection_diagnostics(self.connection, disk=disk)

        by_id = {s.id: s for s in report.steps}
        self.assertEqual(by_id['shallow_list'].status, 'warn')
        self.assertEqual(report.verdict, 'degraded')

    def test_write_probe_for_read_write(self):
        self.connection.write_mode = WriteMode.READ_WRITE
        self.connection.credential_ref = 'YANDEX_DISK_MIKE_RW_TOKEN'
        self.connection.save()

        disk = MagicMock()
        disk.check_token.return_value = True
        disk.exists.side_effect = [True, True]  # root, then probe file
        disk.get_meta.return_value = SimpleNamespace(type='dir', path='/plans', name='plans')
        disk.listdir.return_value = [
            SimpleNamespace(type='file', name='a.plx', path='/plans/a.plx'),
        ]

        with self.settings(YANDEX_DISK_MIKE_RW_TOKEN='rw-token'):
            report = run_connection_diagnostics(self.connection, disk=disk)

        by_id = {s.id: s for s in report.steps}
        self.assertEqual(by_id['write_probe'].status, 'ok')
        disk.upload.assert_called_once()
        disk.remove.assert_called_once()
        self.assertEqual(report.verdict, 'ok')

    def test_invalid_token(self):
        disk = MagicMock()
        disk.check_token.return_value = False

        with self.settings(YANDEX_DISK_UO_READONLY_TOKEN='bad'):
            report = run_connection_diagnostics(self.connection, disk=disk)

        by_id = {s.id: s for s in report.steps}
        self.assertEqual(by_id['token_valid'].status, 'fail')
        self.assertEqual(by_id['root_exists'].status, 'skip')
        self.assertEqual(report.verdict, 'failed')
