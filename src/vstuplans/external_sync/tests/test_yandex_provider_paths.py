from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from external_sync.providers.yandex_disk import YandexDiskProvider, _strip_scheme


class StripSchemeTests(SimpleTestCase):
    def test_strip_disk_prefix(self):
        self.assertEqual(_strip_scheme('disk:/Shared/Plans/a.plx'), '/Shared/Plans/a.plx')

    def test_strip_trash_prefix(self):
        self.assertEqual(_strip_scheme('trash:/old.plx'), '/old.plx')

    def test_already_posix(self):
        self.assertEqual(_strip_scheme('/Shared/Plans'), '/Shared/Plans')

    def test_no_leading_slash(self):
        self.assertEqual(_strip_scheme('Shared/Plans'), '/Shared/Plans')


class YandexProviderPathTests(SimpleTestCase):
    def setUp(self):
        self.disk = MagicMock()
        self.provider = YandexDiskProvider(self.disk, root_path='/Shared/Plans')

    def test_from_remote_strips_disk_and_root(self):
        self.assertEqual(
            self.provider._from_remote_path('disk:/Shared/Plans/ВТФ/a.plx'),
            '/ВТФ/a.plx',
        )

    def test_to_remote_joins_root(self):
        self.assertEqual(self.provider._to_remote_path('/ВТФ/a.plx'), '/Shared/Plans/ВТФ/a.plx')

    def test_to_remote_does_not_double_prefix(self):
        self.assertEqual(
            self.provider._to_remote_path('/Shared/Plans/ВТФ/a.plx'),
            '/Shared/Plans/ВТФ/a.plx',
        )

    def test_to_remote_strips_disk_before_join(self):
        # ошибочный «относительный» путь со схемой не должен дать /Shared/Plans/disk:/...
        self.assertEqual(
            self.provider._to_remote_path('disk:/Shared/Plans/ВТФ/a.plx'),
            '/Shared/Plans/ВТФ/a.plx',
        )

    def test_download_uses_clean_absolute_path(self):
        self.provider.download('/ВТФ/a.plx', 'C:/tmp/a.plx')
        self.disk.download.assert_called_once_with('/Shared/Plans/ВТФ/a.plx', 'C:/tmp/a.plx')

    def test_list_and_download_without_disk_scheme(self):
        self.disk.listdir.side_effect = [
            [
                SimpleNamespace(
                    type='dir',
                    name='ВТФ',
                    path='disk:/Shared/Plans/ВТФ',
                    size=0,
                    modified=None,
                    resource_id='dir1',
                )
            ],
            [
                SimpleNamespace(
                    type='file',
                    name='a.plx',
                    path='disk:/Shared/Plans/ВТФ/a.plx',
                    size=10,
                    modified=None,
                    md5='abc',
                    resource_id='file1',
                )
            ],
        ]

        items = list(self.provider.list('/'))
        files = [i for i in items if not i.is_dir]
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].path, '/ВТФ/a.plx')
        self.assertNotIn('disk:', files[0].path)

        # рекурсия listdir без disk:
        called_paths = [c.args[0] for c in self.disk.listdir.call_args_list]
        self.assertEqual(called_paths[0], '/Shared/Plans')
        self.assertEqual(called_paths[1], '/Shared/Plans/ВТФ')
        self.assertTrue(all('disk:' not in p for p in called_paths))

        self.provider.download(files[0].path, 'C:/tmp/a.plx')
        abs_path = self.disk.download.call_args.args[0]
        self.assertEqual(abs_path, '/Shared/Plans/ВТФ/a.plx')
        self.assertNotIn('disk:', abs_path)

    def test_root_slash_handles_disk_prefix(self):
        provider = YandexDiskProvider(self.disk, root_path='/')
        self.assertEqual(provider._from_remote_path('disk:/file.plx'), '/file.plx')
        self.assertEqual(provider._to_remote_path('/file.plx'), '/file.plx')
        self.assertEqual(provider._to_remote_path('disk:/file.plx'), '/file.plx')
