from __future__ import annotations

import logging
import os

import yadisk
from django.conf import settings

from external_sync.models import ExternalConnection
from external_sync.providers.fake import FakeProvider
from external_sync.providers.yandex_disk import YandexDiskProvider

logger = logging.getLogger(__name__)

CREDENTIAL_ENV_MAP = {
    'YANDEX_DISK_UO_READONLY_TOKEN': 'YANDEX_DISK_UO_READONLY_TOKEN',
    'YANDEX_DISK_MIKE_RW_TOKEN': 'YANDEX_DISK_MIKE_RW_TOKEN',
    'YANDEX_DISK_TOKEN': 'YANDEX_DISK_TOKEN',
}


class ConnectionRegistry:
    def resolve_token(self, credential_ref: str) -> str | None:
        env_name = CREDENTIAL_ENV_MAP.get(credential_ref, credential_ref)
        token = os.getenv(env_name)
        if token:
            return token
        if credential_ref == 'YANDEX_DISK_UO_READONLY_TOKEN':
            return getattr(settings, 'YANDEX_DISK_UO_READONLY_TOKEN', None)
        if credential_ref == 'YANDEX_DISK_MIKE_RW_TOKEN':
            return getattr(settings, 'YANDEX_DISK_MIKE_RW_TOKEN', None)
        return getattr(settings, 'YANDEX_DISK_TOKEN', None)

    def build_provider(self, connection: ExternalConnection):
        if connection.provider_key == 'fake':
            return FakeProvider(read_only=connection.is_read_only_mode())

        token = self.resolve_token(connection.credential_ref)
        if not token:
            raise RuntimeError(f'Не задан токен для {connection.credential_ref}')
        disk = yadisk.YaDisk(token=token)
        if not disk.check_token():
            raise RuntimeError(f'Неверный токен для подключения {connection.slug}')
        return YandexDiskProvider.from_connection(connection, disk)
