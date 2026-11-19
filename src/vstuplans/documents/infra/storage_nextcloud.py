"""Основное хранилище файлов редакций в Nextcloud (WebDAV + OCS shares)."""
from __future__ import annotations

import logging
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import BinaryIO, Iterator
from urllib.parse import quote

import requests
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

_RETRYABLE = frozenset({429, 500, 502, 503, 504})


class NextcloudError(RuntimeError):
    """Ошибка обращения к Nextcloud."""


class NextcloudStoragePort:
    """Хранение по WebDAV; прямые ссылки — через OCS Sharing API."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        public_url: str | None = None,
        username: str | None = None,
        app_password: str | None = None,
        root: str | None = None,
        temp_dir: Path | None = None,
        timeout: float | None = None,
        verify_tls: bool | str | None = None,
        download_mode: str | None = None,
        share_ttl_days: int | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = (base_url if base_url is not None else settings.NEXTCLOUD_URL).rstrip('/')
        self.public_url = (
            public_url
            if public_url is not None
            else getattr(settings, 'NEXTCLOUD_PUBLIC_URL', '') or self.base_url
        ).rstrip('/')
        self.username = username if username is not None else settings.NEXTCLOUD_USER
        self.app_password = (
            app_password if app_password is not None else settings.NEXTCLOUD_APP_PASSWORD
        )
        self.root = (root if root is not None else settings.NEXTCLOUD_ROOT).strip().strip('/')
        self.temp_dir = Path(
            temp_dir if temp_dir is not None else settings.NEXTCLOUD_TEMP_DIR
        )
        self.timeout = (
            timeout if timeout is not None else float(settings.NEXTCLOUD_TIMEOUT_SECONDS)
        )
        self.verify_tls = (
            verify_tls if verify_tls is not None else settings.NEXTCLOUD_VERIFY_TLS
        )
        self.download_mode = (
            download_mode
            if download_mode is not None
            else getattr(settings, 'NEXTCLOUD_DOWNLOAD_MODE', 'direct')
        )
        self.share_ttl_days = (
            share_ttl_days
            if share_ttl_days is not None
            else int(getattr(settings, 'NEXTCLOUD_SHARE_TTL_DAYS', 7))
        )
        self._session = session or requests.Session()
        self._session.auth = (self.username, self.app_password)

    # --- URL helpers ---------------------------------------------------------

    def _dav_base(self) -> str:
        return f'{self.base_url}/remote.php/dav/files/{quote(self.username, safe="")}'

    def _remote_path(self, storage_key: str) -> str:
        key = storage_key.replace('\\', '/').lstrip('/')
        if self.root:
            return f'{self.root}/{key}'
        return key

    def _dav_url(self, storage_key: str) -> str:
        remote = self._remote_path(storage_key)
        parts = [quote(p, safe='') for p in remote.split('/') if p]
        return f'{self._dav_base()}/{"/".join(parts)}'

    def _share_path(self, storage_key: str) -> str:
        return '/' + self._remote_path(storage_key)

    def _download_url(self, token: str, filename: str) -> str:
        safe_name = quote(Path(filename).name or 'file', safe='')
        return f'{self.public_url}/s/{token}/download/{safe_name}'

    # --- HTTP with retries ---------------------------------------------------

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs.setdefault('timeout', self.timeout)
        kwargs.setdefault('verify', self.verify_tls)
        last_exc: BaseException | None = None
        delay = 1.0
        for attempt in range(5):
            try:
                response = self._session.request(method, url, **kwargs)
                if response.status_code in _RETRYABLE and attempt < 4:
                    time.sleep(delay)
                    delay = min(delay * 2, 30.0)
                    continue
                return response
            except requests.RequestException as exc:
                last_exc = exc
                if attempt >= 4:
                    break
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
        if last_exc is not None:
            raise NextcloudError(f'Nextcloud request failed: {last_exc}') from last_exc
        raise NextcloudError(f'Nextcloud request failed after retries: {method} {url}')

    def _ensure_collections(self, storage_key: str) -> None:
        key = storage_key.replace('\\', '/').lstrip('/')
        segments = [s for s in key.split('/')[:-1] if s]
        if self.root:
            prefix_parts = [p for p in self.root.split('/') if p]
        else:
            prefix_parts = []
        accumulated: list[str] = []
        for part in prefix_parts + segments:
            accumulated.append(part)
            url = f'{self._dav_base()}/{"/".join(quote(p, safe="") for p in accumulated)}'
            response = self._request('MKCOL', url)
            if response.status_code in {201, 405, 409}:
                continue
            if response.status_code == 404:
                # parent missing — should not happen if we create in order
                continue
            if response.status_code >= 400 and response.status_code not in {405, 409}:
                raise NextcloudError(
                    f'MKCOL failed ({response.status_code}) for {"/".join(accumulated)}: '
                    f'{response.text[:200]}'
                )

    # --- StoragePort ---------------------------------------------------------

    def save(self, file_path: Path, destination_name: str) -> str:
        key = destination_name.replace('\\', '/').lstrip('/')
        self._ensure_collections(key)
        url = self._dav_url(key)
        with Path(file_path).open('rb') as handle:
            response = self._request(
                'PUT',
                url,
                data=handle,
                headers={'Content-Type': 'application/octet-stream'},
            )
        if response.status_code not in {200, 201, 204}:
            raise NextcloudError(
                f'PUT failed ({response.status_code}) for {key}: {response.text[:200]}'
            )
        return key

    def open_binary(self, storage_key: str) -> bytes:
        with self.open_stream(storage_key) as handle:
            return handle.read()

    def open_stream(self, storage_key: str) -> BinaryIO:
        url = self._dav_url(storage_key)
        response = self._request('GET', url, stream=True)
        if response.status_code == 404:
            raise FileNotFoundError(storage_key)
        if response.status_code != 200:
            raise NextcloudError(
                f'GET failed ({response.status_code}) for {storage_key}: {response.text[:200]}'
            )
        # Materialize so callers can rewind; FileResponse closes the handle.
        tmp = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024)
        for chunk in response.iter_content(chunk_size=65536):
            if chunk:
                tmp.write(chunk)
        tmp.seek(0)
        response.close()
        return tmp

    def delete(self, storage_key: str) -> None:
        url = self._dav_url(storage_key)
        response = self._request('DELETE', url)
        if response.status_code not in {200, 204, 404}:
            raise NextcloudError(
                f'DELETE failed ({response.status_code}) for {storage_key}: {response.text[:200]}'
            )
        self.revoke_direct_urls([storage_key])

    def rename(self, storage_key: str, new_basename: str) -> str:
        old_key = storage_key.replace('\\', '/').lstrip('/')
        new_basename = Path(new_basename).name
        if not new_basename:
            raise ValueError('Empty destination filename')
        new_key = str(Path(old_key).with_name(new_basename)).replace('\\', '/')
        if new_key == old_key:
            return old_key
        if not self.exists(old_key):
            raise FileNotFoundError(old_key)
        if self.exists(new_key):
            raise FileExistsError(new_key)
        self._ensure_collections(new_key)
        dest_url = self._dav_url(new_key)
        response = self._request(
            'MOVE',
            self._dav_url(old_key),
            headers={'Destination': dest_url, 'Overwrite': 'F'},
        )
        if response.status_code == 404:
            raise FileNotFoundError(old_key)
        if response.status_code in {412, 409}:
            raise FileExistsError(new_key)
        if response.status_code not in {201, 204}:
            raise NextcloudError(
                f'MOVE failed ({response.status_code}) for {old_key} → {new_key}: '
                f'{response.text[:200]}'
            )
        # Share is tied to the file id in Nextcloud; update our cache key.
        self._rekey_share(old_key, new_key)
        return new_key

    def exists(self, storage_key: str) -> bool:
        response = self._request(
            'PROPFIND',
            self._dav_url(storage_key),
            headers={'Depth': '0'},
        )
        return response.status_code in {207, 200}

    @contextmanager
    def local_copy(self, storage_key: str) -> Iterator[Path]:
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='nc-copy-', dir=self.temp_dir)
        path = Path(name)
        try:
            import os

            os.close(fd)
            url = self._dav_url(storage_key)
            response = self._request('GET', url, stream=True)
            if response.status_code == 404:
                raise FileNotFoundError(storage_key)
            if response.status_code != 200:
                raise NextcloudError(
                    f'GET failed ({response.status_code}) for {storage_key}: {response.text[:200]}'
                )
            with path.open('wb') as handle:
                for chunk in response.iter_content(chunk_size=65536):
                    if chunk:
                        handle.write(chunk)
            response.close()
            yield path
        finally:
            path.unlink(missing_ok=True)

    def direct_download_url(self, storage_key: str, filename: str) -> str | None:
        if self.download_mode != 'direct':
            return None
        key = storage_key.replace('\\', '/').lstrip('/')
        try:
            return self._get_or_create_share_url(key, filename)
        except Exception as exc:  # noqa: BLE001 — страница/скачивание должны деградировать в proxy
            logger.warning('Failed to create Nextcloud share for %s: %s', key, exc)
            return None

    def revoke_direct_urls(self, storage_keys: list[str]) -> None:
        from documents.models import StorageShareLink

        keys = [k.replace('\\', '/').lstrip('/') for k in storage_keys if k]
        if not keys:
            return
        links = list(StorageShareLink.objects.filter(storage_key__in=keys))
        for link in links:
            try:
                self._delete_share(link.share_id)
            except Exception:  # noqa: BLE001
                logger.exception('Failed to delete Nextcloud share %s', link.share_id)
        StorageShareLink.objects.filter(storage_key__in=keys).delete()

    # --- Shares --------------------------------------------------------------

    def _get_or_create_share_url(self, storage_key: str, filename: str) -> str:
        from documents.models import StorageShareLink

        now = timezone.now()
        refresh_before = now + timedelta(days=1)
        existing = StorageShareLink.objects.filter(storage_key=storage_key).first()
        if existing and existing.expires_at > refresh_before:
            return self._download_url(existing.token, filename)

        if existing:
            try:
                self._delete_share(existing.share_id)
            except Exception:  # noqa: BLE001
                logger.exception('Failed to replace Nextcloud share %s', existing.share_id)
            existing.delete()

        share_id, token, expires_at = self._create_share(storage_key)
        url = self._download_url(token, filename)
        StorageShareLink.objects.create(
            storage_key=storage_key,
            share_id=str(share_id),
            token=token,
            url=url,
            expires_at=expires_at,
        )
        return url

    def _create_share(self, storage_key: str) -> tuple[str, str, datetime]:
        expires_at = timezone.now() + timedelta(days=self.share_ttl_days)
        expire_date = expires_at.date().isoformat()
        url = f'{self.base_url}/ocs/v2.php/apps/files_sharing/api/v1/shares?format=json'
        response = self._request(
            'POST',
            url,
            data={
                'path': self._share_path(storage_key),
                'shareType': 3,
                'permissions': 1,
                'expireDate': expire_date,
            },
            headers={'OCS-APIRequest': 'true'},
        )
        if response.status_code not in {200, 201}:
            raise NextcloudError(
                f'Create share failed ({response.status_code}): {response.text[:300]}'
            )
        payload = response.json()
        data = (payload.get('ocs') or {}).get('data') or {}
        token = data.get('token')
        share_id = data.get('id')
        if not token or share_id is None:
            raise NextcloudError(f'Create share returned no token: {payload!r}')
        return str(share_id), str(token), expires_at

    def _delete_share(self, share_id: str) -> None:
        url = (
            f'{self.base_url}/ocs/v2.php/apps/files_sharing/api/v1/shares/'
            f'{quote(str(share_id), safe="")}?format=json'
        )
        response = self._request(
            'DELETE',
            url,
            headers={'OCS-APIRequest': 'true'},
        )
        if response.status_code not in {100, 200, 404}:
            # OCS sometimes wraps HTTP 200 with statuscode 100
            ocs_meta = ((response.json() if response.content else {}).get('ocs') or {}).get(
                'meta'
            ) or {}
            if ocs_meta.get('statuscode') in {100, 200}:
                return
            if response.status_code == 404:
                return
            raise NextcloudError(
                f'Delete share failed ({response.status_code}): {response.text[:200]}'
            )

    def _rekey_share(self, old_key: str, new_key: str) -> None:
        from documents.models import StorageShareLink

        StorageShareLink.objects.filter(storage_key=old_key).update(storage_key=new_key)

    # --- Diagnostics helpers (check_nextcloud / healthz) ----------------------

    def fetch_capabilities(self) -> dict:
        url = f'{self.base_url}/ocs/v2.php/cloud/capabilities?format=json'
        response = self._request('GET', url, headers={'OCS-APIRequest': 'true'})
        if response.status_code != 200:
            raise NextcloudError(
                f'Capabilities failed ({response.status_code}): {response.text[:200]}'
            )
        return response.json()

    def probe_roundtrip(self) -> dict:
        """Write/read/rename/delete under _check/; returns diagnostics for shares."""
        marker = f'probe-{uuid.uuid4().hex}'
        key = f'_check/{marker}.txt'
        renamed = f'_check/{marker}-renamed.txt'
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        local = self.temp_dir / f'{marker}.txt'
        local.write_text('ok', encoding='utf-8')
        result = {
            'save': False,
            'exists': False,
            'read': False,
            'rename': False,
            'share': False,
            'share_with_filename': False,
            'delete': False,
            'share_url': None,
        }
        try:
            self.save(local, key)
            result['save'] = True
            result['exists'] = self.exists(key)
            data = self.open_binary(key)
            result['read'] = data == b'ok'
            new_key = self.rename(key, Path(renamed).name)
            result['rename'] = new_key == renamed and self.exists(renamed)
            share_id, token, _expires = self._create_share(renamed)
            url_plain = f'{self.public_url}/s/{token}/download'
            url_named = self._download_url(token, 'probe.txt')
            result['share_url'] = url_named
            plain = requests.get(
                url_plain, timeout=self.timeout, verify=self.verify_tls, allow_redirects=True
            )
            result['share'] = plain.status_code == 200 and b'ok' in plain.content
            named = requests.get(
                url_named, timeout=self.timeout, verify=self.verify_tls, allow_redirects=True
            )
            result['share_with_filename'] = (
                named.status_code == 200 and b'ok' in named.content
            )
            self._delete_share(share_id)
            self.delete(renamed)
            result['delete'] = not self.exists(renamed)
        finally:
            local.unlink(missing_ok=True)
            for leftover in (key, renamed):
                try:
                    if self.exists(leftover):
                        self.delete(leftover)
                except Exception:  # noqa: BLE001
                    logger.exception('Cleanup leftover %s', leftover)
        return result
