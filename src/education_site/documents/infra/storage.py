from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings


class UserfilesStoragePort:
    """Stores files under USERFILES_ROOT; storage_key is a relative posix path."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root or settings.USERFILES_ROOT)

    def save(self, file_path: Path, destination_name: str) -> str:
        key = destination_name.replace('\\', '/').lstrip('/')
        dest = self.root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, dest)
        return key

    def open_binary(self, storage_key: str) -> bytes:
        return (self.root / storage_key).read_bytes()

    def delete(self, storage_key: str) -> None:
        path = self.root / storage_key
        if path.exists():
            path.unlink()

    def resolve_path(self, storage_key: str) -> Path:
        return self.root / storage_key
