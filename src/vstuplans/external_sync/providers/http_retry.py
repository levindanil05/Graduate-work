from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar('T')

_RETRYABLE_HTTP = frozenset({429, 500, 502, 503, 504})


def _status_code(exc: BaseException) -> int | None:
    response = getattr(exc, 'response', None)
    if response is None:
        return None
    return getattr(response, 'status_code', None)


def call_with_backoff(
    fn: Callable[[], T],
    *,
    max_attempts: int = 5,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
) -> T:
    delay = initial_delay
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — провайдеры бросают разные типы API
            code = _status_code(exc)
            if code not in _RETRYABLE_HTTP or attempt >= max_attempts - 1:
                raise
            last_exc = exc
            time.sleep(delay)
            delay = min(delay * 2, max_delay)
    if last_exc is not None:
        raise last_exc
    raise RuntimeError('unreachable')
