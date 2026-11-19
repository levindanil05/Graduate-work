"""Локальное хранилище и фабрика порта StoragePort."""
from __future__ import annotations

import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Iterator

from django.conf import settings


def version_storage_key(document_id, version_id) -> str:
    return f'documents/{document_id}/{version_id}.plx'


class UserfilesStoragePort:
    """Stores files under USERFILES_ROOT; storage_key is a relative posix path."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or settings.USERFILES_ROOT)

    @staticmethod
    def version_storage_key(document_id, version_id) -> str:
        return f'documents/{document_id}/{version_id}.plx'

    def save(self, file_path: Path, destination_name: str) -> str:
        key = destination_name.replace('\\', '/').lstrip('/')
        dest = self.root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, dest)
        return key

    def open_binary(self, storage_key: str) -> bytes:
        path = self.resolve_path(storage_key)
        if not path.exists():
            raise FileNotFoundError(storage_key)
        return path.read_bytes()

    def delete(self, storage_key: str) -> None:
        path = self.root / storage_key
        if path.exists():
            path.unlink()

    def resolve_path(self, storage_key: str) -> Path:
        return self.root / storage_key

    def rename(self, storage_key: str, new_basename: str) -> str:
        """Переименовывает файл, сохраняя каталог относительно USERFILES_ROOT."""
        old_key = storage_key.replace('\\', '/').lstrip('/')
        new_basename = Path(new_basename).name
        if not new_basename:
            raise ValueError('Empty destination filename')
        old_path = self.root / old_key
        if not old_path.exists():
            raise FileNotFoundError(old_key)
        new_key = str(Path(old_key).with_name(new_basename)).replace('\\', '/')
        new_path = self.root / new_key
        if new_path.resolve() == old_path.resolve():
            return old_key
        if new_path.exists():
            raise FileExistsError(new_key)
        new_path.parent.mkdir(parents=True, exist_ok=True)
        old_path.rename(new_path)
        return new_key

    def exists(self, storage_key: str) -> bool:
        return self.resolve_path(storage_key).is_file()

    @contextmanager
    def local_copy(self, storage_key: str) -> Iterator[Path]:
        path = self.resolve_path(storage_key)
        if not path.is_file():
            raise FileNotFoundError(storage_key)
        yield path

    def open_stream(self, storage_key: str) -> BinaryIO:
        path = self.resolve_path(storage_key)
        if not path.is_file():
            raise FileNotFoundError(storage_key)
        return path.open('rb')

    def direct_download_url(self, storage_key: str, filename: str) -> str | None:
        return None

    def revoke_direct_urls(self, storage_keys: list[str]) -> None:
        return None


LocalStoragePort = UserfilesStoragePort


def build_storage_port():
    """Выбирает реализацию хранилища по settings.STORAGE_BACKEND."""
    backend = getattr(settings, 'STORAGE_BACKEND', 'local')
    if backend == 'nextcloud':
        from documents.infra.storage_nextcloud import NextcloudStoragePort

        return NextcloudStoragePort()
    return LocalStoragePort()
