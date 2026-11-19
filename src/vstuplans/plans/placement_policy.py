from __future__ import annotations

from pathlib import PurePosixPath

from external_sync.models import RemoteRole


def classify_path(remote_path: str) -> str:
    """Return active, archive or ignored for a remote PLX path."""
    parts = PurePosixPath(remote_path.replace('\\', '/')).parts
    for part in parts:
        if part.lower() == 'архив':
            return RemoteRole.ARCHIVE
    if remote_path.lower().endswith('.plx'):
        return RemoteRole.ACTIVE
    return RemoteRole.IGNORED


def relative_path_from_root(remote_path: str, root_path: str = '/') -> str:
    path = remote_path.replace('\\', '/')
    root = (root_path or '/').rstrip('/')
    if root and root != '/':
        prefix = root + '/'
        if path.startswith(prefix):
            return path[len(prefix) :]
        if path == root:
            return ''
    return path.lstrip('/')


def primary_active_path(existing_paths: list[str], imported_path: str) -> str:
    if imported_path:
        return imported_path
    active = [p for p in existing_paths if classify_path(p) == RemoteRole.ACTIVE]
    if active:
        return sorted(active)[0]
    return imported_path


def archive_directory_for_active(active_path: str) -> str:
    parent = str(PurePosixPath(active_path).parent).replace('\\', '/')
    if parent in ('', '.'):
        return 'Архив'
    return f'{parent}/Архив'


def build_active_path_from_metadata(metadata: dict, source_filename: str) -> str:
    faculty = metadata.get('faculty_abbr_ru') or metadata.get('faculty') or 'PLX'
    department = metadata.get('department_abbr_ru') or metadata.get('department') or ''
    name = PurePosixPath(source_filename).name
    if department:
        return f'{faculty}/{department}/{name}'
    return f'{faculty}/{name}'
