"""Ограничение частоты попыток входа."""
from __future__ import annotations

import time
from collections import defaultdict
from threading import Lock

from django.conf import settings
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden


class LoginRateLimitMiddleware:
    """Простой in-memory лимит попыток POST на /accounts/login/."""

    _attempts: dict[str, list[float]] = defaultdict(list)
    _lock = Lock()

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.method == 'POST' and request.path.rstrip('/').endswith('/accounts/login'):
            client_ip = self._client_ip(request)
            max_attempts = getattr(settings, 'LOGIN_RATE_LIMIT_ATTEMPTS', 5)
            window = getattr(settings, 'LOGIN_RATE_LIMIT_WINDOW_SECONDS', 900)
            now = time.monotonic()
            with self._lock:
                recent = [t for t in self._attempts[client_ip] if now - t < window]
                self._attempts[client_ip] = recent
                if len(recent) >= max_attempts:
                    return HttpResponseForbidden(
                        'Слишком много попыток входа. Попробуйте позже.'
                    )
        response = self.get_response(request)
        if (
            request.method == 'POST'
            and request.path.rstrip('/').endswith('/accounts/login')
            and getattr(response, 'status_code', 200) == 200
            and not request.user.is_authenticated
        ):
            # Неудачный вход (форма снова показана)
            client_ip = self._client_ip(request)
            with self._lock:
                self._attempts[client_ip].append(time.monotonic())
        elif request.user.is_authenticated:
            client_ip = self._client_ip(request)
            with self._lock:
                self._attempts.pop(client_ip, None)
        return response

    @staticmethod
    def _client_ip(request: HttpRequest) -> str:
        # Доверяем X-Forwarded-For только если прокси включён (USE_X_FORWARDED_HOST).
        if getattr(settings, 'USE_X_FORWARDED_HOST', False):
            forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
            if forwarded:
                return forwarded.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR', 'unknown')
