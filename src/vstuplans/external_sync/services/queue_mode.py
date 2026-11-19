from __future__ import annotations


def encode_queue_idempotency_key(mode: str) -> str:
    """Режим прогона в префиксе ключа: full | pull | push."""
    normalized = mode if mode in {'full', 'pull', 'push'} else 'full'
    from uuid import uuid4

    return f'{normalized}:{uuid4().hex}'


def parse_queue_mode(idempotency_key: str) -> str:
    if not idempotency_key:
        return 'full'
    head = idempotency_key.split(':', 1)[0]
    if head in {'full', 'pull', 'push'}:
        return head
    return 'full'
