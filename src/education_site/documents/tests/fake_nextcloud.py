"""In-memory Nextcloud (WebDAV + OCS shares) for unit tests."""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from urllib.parse import unquote, urlparse

import requests


@dataclass
class FakeResponse:
    status_code: int
    content: bytes = b''
    headers: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.content.decode('utf-8', errors='replace')

    def json(self):
        return json.loads(self.content.decode('utf-8') or '{}')

    def iter_content(self, chunk_size=65536):
        data = self.content
        for i in range(0, len(data), chunk_size):
            yield data[i : i + chunk_size]

    def close(self):
        return None


class FakeNextcloudSession:
    """Drop-in for requests.Session used by NextcloudStoragePort."""

    def __init__(self, *, base_url: str = 'https://nc.test', username: str = 'app'):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.auth = None
        self.files: dict[str, bytes] = {}
        self.dirs: set[str] = {''}
        self.shares: dict[str, dict] = {}
        self.get_count = 0
        self.put_count = 0
        self.share_create_count = 0
        self.fail_share = False
        self.fail_named_download = False

    def request(self, method: str, url: str, **kwargs) -> FakeResponse:
        method = method.upper()
        parsed = urlparse(url)
        path = unquote(parsed.path)

        if '/ocs/v2.php/cloud/capabilities' in path:
            return self._capabilities()
        if '/ocs/v2.php/apps/files_sharing/api/v1/shares' in path:
            return self._shares(method, path, kwargs)

        dav_prefix = f'/remote.php/dav/files/{self.username}'
        if path.startswith(dav_prefix):
            rel = path[len(dav_prefix) :].lstrip('/')
            return self._dav(method, rel, kwargs)

        if path.startswith('/s/') and '/download' in path:
            return self._public_download(path)

        return FakeResponse(404, b'not found')

    def get(self, url: str, **kwargs) -> FakeResponse:
        return self.request('GET', url, **kwargs)

    def _capabilities(self) -> FakeResponse:
        payload = {
            'ocs': {
                'meta': {'statuscode': 200},
                'data': {
                    'version': {'string': '29.0.0'},
                    'capabilities': {
                        'files_sharing': {
                            'public': {
                                'enabled': True,
                                'expire_date': {'enabled': True, 'days': 7, 'enforced': False},
                            }
                        }
                    },
                },
            }
        }
        return FakeResponse(200, json.dumps(payload).encode('utf-8'))

    def _dav(self, method: str, rel: str, kwargs: dict) -> FakeResponse:
        rel = rel.strip('/')
        if method == 'MKCOL':
            parent = '/'.join(rel.split('/')[:-1]) if '/' in rel else ''
            if parent and parent not in self.dirs and parent not in self.files:
                # allow creating if parent exists or empty
                if parent and parent not in self.dirs:
                    return FakeResponse(409, b'conflict')
            if rel in self.dirs:
                return FakeResponse(405, b'exists')
            self.dirs.add(rel)
            # ensure parents
            parts = rel.split('/')
            for i in range(len(parts)):
                self.dirs.add('/'.join(parts[: i + 1]))
            return FakeResponse(201, b'')

        if method == 'PUT':
            data = kwargs.get('data')
            if hasattr(data, 'read'):
                content = data.read()
            else:
                content = data or b''
            if isinstance(content, str):
                content = content.encode('utf-8')
            parent = '/'.join(rel.split('/')[:-1])
            if parent:
                self.dirs.add(parent)
            self.files[rel] = content
            self.put_count += 1
            return FakeResponse(201, b'')

        if method == 'GET':
            self.get_count += 1
            if rel not in self.files:
                return FakeResponse(404, b'missing')
            return FakeResponse(200, self.files[rel])

        if method == 'DELETE':
            if rel in self.files:
                del self.files[rel]
                return FakeResponse(204, b'')
            if rel in self.dirs:
                self.dirs.discard(rel)
                # remove nested
                prefix = rel + '/'
                for key in list(self.files):
                    if key.startswith(prefix):
                        del self.files[key]
                return FakeResponse(204, b'')
            return FakeResponse(404, b'')

        if method == 'MOVE':
            headers = kwargs.get('headers') or {}
            dest = headers.get('Destination') or headers.get('destination') or ''
            dest_path = unquote(urlparse(dest).path)
            prefix = f'/remote.php/dav/files/{self.username}/'
            if not dest_path.startswith(prefix):
                return FakeResponse(400, b'bad dest')
            new_rel = dest_path[len(prefix) :].strip('/')
            if rel not in self.files:
                return FakeResponse(404, b'')
            if new_rel in self.files and headers.get('Overwrite') == 'F':
                return FakeResponse(412, b'exists')
            self.files[new_rel] = self.files.pop(rel)
            return FakeResponse(201, b'')

        if method == 'PROPFIND':
            if rel in self.files or rel in self.dirs or rel == '':
                return FakeResponse(207, b'<multistatus/>')
            return FakeResponse(404, b'')

        return FakeResponse(405, b'')

    def _shares(self, method: str, path: str, kwargs: dict) -> FakeResponse:
        if method == 'POST':
            if self.fail_share:
                return FakeResponse(403, b'forbidden')
            data = kwargs.get('data') or {}
            share_path = (data.get('path') or '').lstrip('/')
            if share_path not in self.files:
                return FakeResponse(404, json.dumps({'ocs': {'meta': {'statuscode': 404}}}).encode())
            share_id = str(len(self.shares) + 1)
            token = uuid.uuid4().hex[:16]
            self.shares[share_id] = {'path': share_path, 'token': token}
            self.share_create_count += 1
            payload = {
                'ocs': {
                    'meta': {'statuscode': 200},
                    'data': {'id': int(share_id), 'token': token},
                }
            }
            return FakeResponse(200, json.dumps(payload).encode('utf-8'))

        if method == 'DELETE':
            match = re.search(r'/shares/([^/?]+)', path)
            share_id = match.group(1) if match else ''
            self.shares.pop(share_id, None)
            return FakeResponse(200, json.dumps({'ocs': {'meta': {'statuscode': 100}}}).encode())

        return FakeResponse(405, b'')

    def _public_download(self, path: str) -> FakeResponse:
        # /s/{token}/download or /s/{token}/download/{filename}
        parts = path.strip('/').split('/')
        # s, token, download, [filename]
        if len(parts) < 3:
            return FakeResponse(404, b'')
        token = parts[1]
        filename = parts[3] if len(parts) > 3 else ''
        if filename and self.fail_named_download:
            return FakeResponse(404, b'')
        for share in self.shares.values():
            if share['token'] == token:
                content = self.files.get(share['path'], b'')
                return FakeResponse(200, content)
        return FakeResponse(404, b'')


def build_fake_nextcloud_port(tmp_path, session: FakeNextcloudSession | None = None):
    from documents.infra.storage_nextcloud import NextcloudStoragePort

    session = session or FakeNextcloudSession()
    return NextcloudStoragePort(
        base_url=session.base_url,
        public_url=session.base_url,
        username=session.username,
        app_password='secret',
        root='plans',
        temp_dir=tmp_path,
        timeout=5,
        verify_tls=True,
        download_mode='direct',
        share_ttl_days=7,
        session=session,
    ), session
