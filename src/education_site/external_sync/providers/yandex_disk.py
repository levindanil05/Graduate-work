from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

import yadisk

from external_sync.models import ExternalConnection, WriteMode
from external_sync.ports import ExternalStorageProvider, ProviderCapabilities, ReadOnlyStorageError, RemoteStat


def _parse_modified(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return None


class YandexDiskProvider(ExternalStorageProvider):
    def __init__(self, disk: yadisk.YaDisk, *, read_only: bool = False, root_path: str = '/') -> None:
        self.disk = disk
        self.read_only = read_only
        self.root_path = root_path.rstrip('/') or '/'

    @classmethod
    def from_connection(cls, connection: ExternalConnection, disk: yadisk.YaDisk) -> YandexDiskProvider:
        return cls(
            disk,
            read_only=connection.write_mode == WriteMode.READ_ONLY,
            root_path=connection.root_path,
        )

    def _guard_write(self) -> None:
        if self.read_only:
            raise ReadOnlyStorageError('Подключение только для чтения')

    def _to_remote_path(self, path: str) -> str:
        path = path.replace('\\', '/')
        if not path.startswith('/'):
            path = '/' + path
        if self.root_path != '/':
            if path == '/':
                return self.root_path
            return self.root_path.rstrip('/') + path
        return path

    def _from_remote_path(self, absolute: str) -> str:
        absolute = absolute.replace('\\', '/')
        if self.root_path != '/':
            base = self.root_path.rstrip('/')
            if absolute.startswith(base):
                suffix = absolute[len(base) :]
                return suffix if suffix.startswith('/') else '/' + suffix
        return absolute

    def list(self, root: str):
        start = self._to_remote_path(root)

        def walk(path: str):
            offset = 0
            while True:
                batch = list(self.disk.listdir(path, limit=1000, offset=offset))
                if not batch:
                    break
                for item in batch:
                    if item.type == 'dir':
                        yield RemoteStat(
                            path=self._from_remote_path(item.path),
                            name=item.name,
                            is_dir=True,
                            size=0,
                            modified_at=_parse_modified(getattr(item, 'modified', None)),
                            md5=None,
                            remote_id=getattr(item, 'resource_id', None) or getattr(item, 'md5', None),
                        )
                        yield from walk(item.path)
                    elif item.name.lower().endswith('.plx'):
                        yield RemoteStat(
                            path=self._from_remote_path(item.path),
                            name=item.name,
                            is_dir=False,
                            size=int(getattr(item, 'size', 0) or 0),
                            modified_at=_parse_modified(getattr(item, 'modified', None)),
                            md5=getattr(item, 'md5', None),
                            remote_id=getattr(item, 'resource_id', None),
                        )
                if len(batch) < 1000:
                    break
                offset += len(batch)

        yield from walk(start)

    def stat(self, path: str) -> RemoteStat:
        absolute = self._to_remote_path(path)
        meta = self.disk.get_meta(absolute)
        return RemoteStat(
            path=self._from_remote_path(meta.path),
            name=meta.name,
            is_dir=meta.type == 'dir',
            size=int(getattr(meta, 'size', 0) or 0),
            modified_at=_parse_modified(getattr(meta, 'modified', None)),
            md5=getattr(meta, 'md5', None),
            remote_id=getattr(meta, 'resource_id', None),
        )

    def download(self, path: str, local_path: str) -> None:
        absolute = self._to_remote_path(path)
        self.disk.download(absolute, local_path)

    def upload(self, local_path: str, dest_path: str, *, overwrite: bool = False) -> None:
        self._guard_write()
        absolute = self._to_remote_path(dest_path)
        parent = str(PurePosixPath(absolute).parent)
        if parent and parent != '/':
            self.mkdirs(self._from_remote_path(parent))
        self.disk.upload(local_path, absolute, overwrite=overwrite)

    def move(self, from_path: str, to_path: str, *, overwrite: bool = False) -> None:
        self._guard_write()
        src = self._to_remote_path(from_path)
        dst = self._to_remote_path(to_path)
        parent = str(PurePosixPath(dst).parent)
        if parent and parent != '/':
            self.mkdirs(self._from_remote_path(parent))
        self.disk.move(src, dst, overwrite=overwrite)

    def mkdirs(self, path: str) -> None:
        self._guard_write()
        absolute = self._to_remote_path(path)
        parts = PurePosixPath(absolute).parts
        current = ''
        for part in parts:
            if part == '/':
                current = '/'
                continue
            current = str(PurePosixPath(current) / part)
            if not self.disk.exists(current):
                self.disk.mkdir(current)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_md5=True,
            supports_resource_id=True,
            supports_async_ops=True,
            supports_browse_url=True,
        )

    def browse_url(self, remote_path: str) -> str | None:
        try:
            absolute = self._to_remote_path(remote_path)
            return self.disk.get_meta(absolute).href
        except Exception:  # noqa: BLE001
            return None


class ReadOnlyYandexDiskProvider(YandexDiskProvider):
    def __init__(self, disk: yadisk.YaDisk, *, root_path: str = '/') -> None:
        super().__init__(disk, read_only=True, root_path=root_path)
