from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Protocol


@dataclass(frozen=True)
class RemoteStat:
    path: str
    name: str
    is_dir: bool
    size: int
    modified_at: datetime | None
    md5: str | None = None
    remote_id: str | None = None


@dataclass(frozen=True)
class ProviderCapabilities:
    supports_md5: bool = False
    supports_resource_id: bool = False
    supports_async_ops: bool = False
    supports_browse_url: bool = False


class ReadOnlyStorageError(PermissionError):
    """Write operation blocked for read-only connection."""


class ExternalStorageProvider(Protocol):
    def list(self, root: str) -> Iterable[RemoteStat]:
        ...

    def stat(self, path: str) -> RemoteStat:
        ...

    def download(self, path: str, local_path: str) -> None:
        ...

    def upload(self, local_path: str, dest_path: str, *, overwrite: bool = False) -> None:
        ...

    def move(self, from_path: str, to_path: str, *, overwrite: bool = False) -> None:
        ...

    def mkdirs(self, path: str) -> None:
        ...

    def capabilities(self) -> ProviderCapabilities:
        ...

    def browse_url(self, remote_path: str) -> str | None:
        ...
