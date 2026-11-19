from __future__ import annotations

import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from documents.tests.fake_nextcloud import build_fake_nextcloud_port


@override_settings(
    NEXTCLOUD_URL='https://nc.test',
    NEXTCLOUD_USER='app',
    NEXTCLOUD_APP_PASSWORD='secret',
    NEXTCLOUD_ROOT='plans',
    NEXTCLOUD_DOWNLOAD_MODE='direct',
    NEXTCLOUD_SHARE_TTL_DAYS=7,
    NEXTCLOUD_VERIFY_TLS=True,
)
class CheckNextcloudCommandTests(TestCase):
    def test_check_succeeds_against_fake(self):
        tmp = tempfile.TemporaryDirectory()
        try:
            port, session = build_fake_nextcloud_port(Path(tmp.name))
            out = StringIO()
            with patch(
                'documents.infra.storage_nextcloud.NextcloudStoragePort',
                return_value=port,
            ):
                with patch('requests.get', side_effect=session.get):
                    call_command('check_nextcloud', stdout=out)
            text = out.getvalue()
            self.assertIn('Готово', text)
            self.assertIn('OK', text)
        finally:
            tmp.cleanup()
