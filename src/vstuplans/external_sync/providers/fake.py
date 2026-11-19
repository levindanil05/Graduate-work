from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from external_sync.ports import ExternalStorageProvider, ProviderCapabilities, ReadOnlyStorageError, RemoteStat


class FakeProvider(ExternalStorageProvider):
    """In-memory filesystem for tests."""

    def __init__(self, *, read_only: bool = False, root: str = '/') -> None:
        self.read_only = read_only
        self.root = root.rstrip('/') or '/'
        self._files: dict[str, tuple[bytes, datetime | None, str | None]] = {}

    def seed_file(
        self,
        rel_path: str,
        content: bytes,
        *,
        modified_at: datetime | None = None,
        md5: str | None = None,
    ) -> None:
        path = self._full(rel_path)
        self._files[path] = (content, modified_at or datetime.now(timezone.utc), md5)

    def _full(self, path: str) -> str:
        path = path.replace('\\', '/')
        if not path.startswith('/'):
            path = '/' + path
        if self.root != '/':
            base = self.root.rstrip('/')
            if path == '/':
                return base
            return base + path
        return path

    def _rel(self, full: str) -> str:
        if self.root != '/':
            base = self.root.rstrip('/')
            if full.startswith(base):
                suffix = full[len(base) :]
                return suffix if suffix.startswith('/') else '/' + suffix
        return full

    def list(self, root: str) -> list[RemoteStat]:
        prefix = self._full(root)
        results: list[RemoteStat] = []
        seen_dirs: set[str] = set()
        for path in sorted(self._files):
            if not path.startswith(prefix.rstrip('/') + '/') and path != prefix.rstrip('/'):
                continue
            rel = self._rel(path)
            name = Path(rel).name
            content, modified_at, md5 = self._files[path]
            results.append(
                RemoteStat(
                    path=rel,
                    name=name,
                    is_dir=False,
                    size=len(content),
                    modified_at=modified_at,
                    md5=md5,
                    remote_id=rel,
                )
            )
            parent = str(Path(rel).parent).replace('\\', '/')
            while parent and parent not in ('.', '/'):
                if parent not in seen_dirs:
                    seen_dirs.add(parent)
                parent = str(Path(parent).parent).replace('\\', '/')
        return results

    def stat(self, path: str) -> RemoteStat:
        full = self._full(path)
        if full not in self._files:
            raise FileNotFoundError(path)
        content, modified_at, md5 = self._files[full]
        rel = self._rel(full)
        return RemoteStat(
            path=rel,
            name=Path(rel).name,
            is_dir=False,
            size=len(content),
            modified_at=modified_at,
            md5=md5,
            remote_id=rel,
        )

    def download(self, path: str, local_path: str) -> None:
        full = self._full(path)
        if full not in self._files:
            raise FileNotFoundError(path)
        Path(local_path).write_bytes(self._files[full][0])

    def upload(self, local_path: str, dest_path: str, *, overwrite: bool = False) -> None:
        if self.read_only:
            raise ReadOnlyStorageError('Read-only provider')
        full = self._full(dest_path)
        if not overwrite and full in self._files:
            raise FileExistsError(dest_path)
        self._files[full] = (Path(local_path).read_bytes(), datetime.now(timezone.utc), None)

    def move(self, from_path: str, to_path: str, *, overwrite: bool = False) -> None:
        if self.read_only:
            raise ReadOnlyStorageError('Read-only provider')
        src = self._full(from_path)
        dst = self._full(to_path)
        if src not in self._files:
            raise FileNotFoundError(from_path)
        if not overwrite and dst in self._files:
            raise FileExistsError(to_path)
        self._files[dst] = self._files.pop(src)

    def mkdirs(self, path: str) -> None:
        if self.read_only:
            raise ReadOnlyStorageError('Read-only provider')

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_md5=True,
            supports_resource_id=True,
            supports_async_ops=False,
            supports_browse_url=False,
        )

    def browse_url(self, remote_path: str) -> str | None:
        return None
