from __future__ import annotations

import hashlib
from pathlib import Path


class HashingService:
    def hash_file(self, file_path: Path) -> str:
        try:
            import xxhash
        except ImportError:
            return self._sha256(file_path)
        digest = xxhash.xxh64()
        with file_path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(65536), b''):
                digest.update(chunk)
        return digest.hexdigest()

    def _sha256(self, file_path: Path) -> str:
        digest = hashlib.sha256()
        with file_path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(65536), b''):
                digest.update(chunk)
        return digest.hexdigest()
