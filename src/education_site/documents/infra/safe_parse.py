"""Безопасный разбор PLX с таймаутом в отдельном процессе."""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path


def _ensure_src_on_path() -> None:
    # src/ (родитель education_site) — там лежит plx_parser.py
    here = Path(__file__).resolve()
    src_root = here.parents[3]  # .../src/education_site/documents/infra -> src
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))


def _parse_worker(path: str) -> dict:
    _ensure_src_on_path()
    from plx_parser import parse_plx_file

    return parse_plx_file(path)


def parse_plx_with_timeout(file_path: Path, timeout_seconds: int = 10) -> dict:
    """Разбор PLX; при превышении времени — словарь с error."""
    path = str(file_path)
    try:
        with ProcessPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_parse_worker, path)
            return future.result(timeout=timeout_seconds)
    except FuturesTimeout:
        return {
            'error': f'Разбор файла превысил {timeout_seconds} с',
            'filename': Path(path).name,
        }
    except Exception as exc:  # noqa: BLE001
        return {'error': str(exc), 'filename': Path(path).name}
