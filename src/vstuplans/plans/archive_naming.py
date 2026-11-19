from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
from zoneinfo import ZoneInfo

MOSCOW = ZoneInfo('Europe/Moscow')


def archive_suffix(version_created_at: datetime) -> str:
    local = version_created_at.astimezone(MOSCOW)
    return local.strftime('%Y-%m-%d')


def archive_suffix_with_time(version_created_at: datetime) -> str:
    local = version_created_at.astimezone(MOSCOW)
    return local.strftime('%Y-%m-%d %H-%M-%S')


def apply_archive_suffix(base_name: str, version_created_at: datetime, *, with_time: bool = False) -> str:
    stem = PurePosixPath(base_name).stem
    suffix = archive_suffix_with_time(version_created_at) if with_time else archive_suffix(version_created_at)
    return f'{stem} ({suffix}).plx'


def choose_archive_filename(
    base_name: str,
    version_created_at: datetime,
    occupied_names: set[str],
) -> str:
    candidate = apply_archive_suffix(base_name, version_created_at)
    if candidate not in occupied_names:
        return candidate
    return apply_archive_suffix(base_name, version_created_at, with_time=True)
