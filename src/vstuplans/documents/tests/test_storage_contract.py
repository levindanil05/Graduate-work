from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings

from documents.infra.storage import LocalStoragePort
from documents.tests.fake_nextcloud import build_fake_nextcloud_port


class _StorageContractMixin:
    storage = None

    def _write_src(self, name: str = 'a.plx', content: bytes = b'hello') -> Path:
        fd, path = tempfile.mkstemp(suffix=name)
        import os

        os.close(fd)
        p = Path(path)
        p.write_bytes(content)
        return p

    def test_save_open_exists_delete(self):
        src = self._write_src()
        try:
            key = self.storage.save(src, 'documents/d1/v1.plx')
            self.assertEqual(key, 'documents/d1/v1.plx')
            self.assertTrue(self.storage.exists(key))
            self.assertEqual(self.storage.open_binary(key), b'hello')
            with self.storage.open_stream(key) as stream:
                self.assertEqual(stream.read(), b'hello')
            self.storage.delete(key)
            self.assertFalse(self.storage.exists(key))
            self.storage.delete(key)  # idempotent
        finally:
            src.unlink(missing_ok=True)

    def test_rename_semantics(self):
        src = self._write_src()
        try:
            key = self.storage.save(src, 'documents/d1/old.plx')
            same = self.storage.rename(key, 'old.plx')
            self.assertEqual(same, key)
            new_key = self.storage.rename(key, 'new.plx')
            self.assertEqual(new_key, 'documents/d1/new.plx')
            self.assertTrue(self.storage.exists(new_key))
            self.assertFalse(self.storage.exists(key))
            other = self._write_src(content=b'other')
            try:
                self.storage.save(other, 'documents/d1/taken.plx')
                with self.assertRaises(FileExistsError):
                    self.storage.rename(new_key, 'taken.plx')
            finally:
                other.unlink(missing_ok=True)
            with self.assertRaises(FileNotFoundError):
                self.storage.rename('documents/d1/missing.plx', 'x.plx')
        finally:
            src.unlink(missing_ok=True)

    def test_local_copy(self):
        src = self._write_src(content=b'copy-me')
        try:
            key = self.storage.save(src, 'documents/d1/c.plx')
            with self.storage.local_copy(key) as path:
                self.assertTrue(path.is_file())
                self.assertEqual(path.read_bytes(), b'copy-me')
        finally:
            src.unlink(missing_ok=True)


@override_settings(STORAGE_BACKEND='local')
class LocalStorageContractTests(_StorageContractMixin, SimpleTestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.storage = LocalStoragePort(root=Path(self._tmpdir.name))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_direct_url_is_none(self):
        self.assertIsNone(self.storage.direct_download_url('a', 'a.plx'))


class NextcloudStorageContractTests(_StorageContractMixin, TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.storage, self.session = build_fake_nextcloud_port(Path(self._tmpdir.name))

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_direct_download_url_creates_share_without_get(self):
        src = self._write_src()
        try:
            key = self.storage.save(src, 'documents/d1/v1.plx')
            before = self.session.get_count
            url = self.storage.direct_download_url(key, 'plan.plx')
            self.assertIsNotNone(url)
            self.assertIn('/s/', url)
            self.assertIn('/download/plan.plx', url)
            self.assertEqual(self.session.get_count, before)
            # second call reuses DB cache
            url2 = self.storage.direct_download_url(key, 'plan.plx')
            self.assertEqual(url, url2)
            self.assertEqual(self.session.share_create_count, 1)
        finally:
            src.unlink(missing_ok=True)

    def test_proxy_mode_returns_none(self):
        self.storage.download_mode = 'proxy'
        src = self._write_src()
        try:
            key = self.storage.save(src, 'documents/d1/v1.plx')
            self.assertIsNone(self.storage.direct_download_url(key, 'plan.plx'))
        finally:
            src.unlink(missing_ok=True)

    def test_revoke_direct_urls(self):
        src = self._write_src()
        try:
            key = self.storage.save(src, 'documents/d1/v1.plx')
            self.storage.direct_download_url(key, 'plan.plx')
            from documents.models import StorageShareLink

            self.assertEqual(StorageShareLink.objects.filter(storage_key=key).count(), 1)
            self.storage.revoke_direct_urls([key])
            self.assertEqual(StorageShareLink.objects.filter(storage_key=key).count(), 0)
        finally:
            src.unlink(missing_ok=True)
