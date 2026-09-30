from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

import yadisk

from external_sync.models import ExternalConnection, WriteMode
from external_sync.registry import CREDENTIAL_ENV_MAP, ConnectionRegistry

PROBE_FILENAME = '.__plx_diag_probe__.tmp'
DEFAULT_LIST_LIMIT = 30


@dataclass
class DiagStep:
    id: str
    title: str
    status: str  # ok | fail | skip | warn
    detail: str
    duration_ms: int = 0


@dataclass
class DiagnosticReport:
    connection_slug: str
    connection_name: str
    verdict: str  # ok | degraded | failed
    steps: list[DiagStep] = field(default_factory=list)

    def add(self, step: DiagStep) -> None:
        self.steps.append(step)

    def to_dict(self) -> dict:
        return {
            'connection_slug': self.connection_slug,
            'connection_name': self.connection_name,
            'verdict': self.verdict,
            'steps': [
                {
                    'id': s.id,
                    'title': s.title,
                    'status': s.status,
                    'detail': s.detail,
                    'duration_ms': s.duration_ms,
                }
                for s in self.steps
            ],
        }


def _status_label(status: str) -> str:
    return {
        'ok': 'Успех',
        'fail': 'Ошибка',
        'skip': 'Пропущено',
        'warn': 'Предупреждение',
    }.get(status, status)


def _timed(fn):
    started = time.perf_counter()
    try:
        result = fn()
        ms = int((time.perf_counter() - started) * 1000)
        return result, ms, None
    except Exception as exc:  # noqa: BLE001
        ms = int((time.perf_counter() - started) * 1000)
        return None, ms, exc


def _normalize_root(root_path: str) -> str:
    path = (root_path or '/').replace('\\', '/')
    if not path.startswith('/'):
        path = '/' + path
    if path != '/' and path.endswith('/'):
        path = path.rstrip('/')
    return path or '/'


def run_connection_diagnostics(
    connection: ExternalConnection,
    *,
    list_limit: int = DEFAULT_LIST_LIMIT,
    disk: yadisk.YaDisk | None = None,
) -> DiagnosticReport:
    """Короткая диагностика подключения без рекурсивного inventory."""
    report = DiagnosticReport(
        connection_slug=connection.slug,
        connection_name=connection.name,
        verdict='ok',
    )
    registry = ConnectionRegistry()
    root = _normalize_root(connection.root_path)
    env_name = CREDENTIAL_ENV_MAP.get(connection.credential_ref, connection.credential_ref)

    # --- config ---
    report.add(
        DiagStep(
            id='config',
            title='Параметры подключения',
            status='ok',
            detail=(
                f'Код: {connection.slug}; режим: {connection.get_write_mode_display()}; '
                f'путь: {root}; секрет: {connection.credential_ref}; '
                f'включено: {"да" if connection.enabled else "нет"}; '
                f'получение: {"вкл" if connection.pull_enabled else "выкл"}; '
                f'отправка: {"вкл" if connection.push_enabled else "выкл"}'
            ),
        )
    )

    chain_ok = True

    # --- token_present ---
    token = registry.resolve_token(connection.credential_ref)
    if token:
        report.add(
            DiagStep(
                id='token_present',
                title='Токен в окружении',
                status='ok',
                detail=f'Переменная «{env_name}» задана (значение не показывается).',
            )
        )
    else:
        report.add(
            DiagStep(
                id='token_present',
                title='Токен в окружении',
                status='fail',
                detail=f'Переменная «{env_name}» пуста или не задана.',
            )
        )
        chain_ok = False

    # --- token_valid ---
    ya_disk = disk
    if not chain_ok:
        report.add(
            DiagStep(
                id='token_valid',
                title='Авторизация API',
                status='skip',
                detail='Пропущено: нет токена.',
            )
        )
    else:
        if ya_disk is None:
            ya_disk = yadisk.YaDisk(token=token)

        def _check():
            return bool(ya_disk.check_token())

        valid, ms, err = _timed(_check)
        if err is not None:
            report.add(
                DiagStep(
                    id='token_valid',
                    title='Авторизация API',
                    status='fail',
                    detail=f'Ошибка проверки токена: {err}',
                    duration_ms=ms,
                )
            )
            chain_ok = False
        elif valid:
            report.add(
                DiagStep(
                    id='token_valid',
                    title='Авторизация API',
                    status='ok',
                    detail='Токен принят API Яндекс.Диска.',
                    duration_ms=ms,
                )
            )
        else:
            report.add(
                DiagStep(
                    id='token_valid',
                    title='Авторизация API',
                    status='fail',
                    detail='API отклонил токен (check_token = False).',
                    duration_ms=ms,
                )
            )
            chain_ok = False

    # --- root_exists ---
    if not chain_ok:
        report.add(
            DiagStep(
                id='root_exists',
                title='Путь существует',
                status='skip',
                detail='Пропущено: нет рабочей авторизации.',
            )
        )
        report.add(
            DiagStep(
                id='root_is_dir',
                title='Путь — папка',
                status='skip',
                detail='Пропущено.',
            )
        )
        report.add(
            DiagStep(
                id='shallow_list',
                title='Содержимое верхнего уровня',
                status='skip',
                detail='Пропущено.',
            )
        )
    else:
        assert ya_disk is not None

        def _exists():
            return ya_disk.exists(root)

        exists, ms, err = _timed(_exists)
        if err is not None:
            report.add(
                DiagStep(
                    id='root_exists',
                    title='Путь существует',
                    status='fail',
                    detail=f'Ошибка exists({root}): {err}',
                    duration_ms=ms,
                )
            )
            chain_ok = False
        elif exists:
            report.add(
                DiagStep(
                    id='root_exists',
                    title='Путь существует',
                    status='ok',
                    detail=f'Путь «{root}» найден на диске.',
                    duration_ms=ms,
                )
            )
        else:
            report.add(
                DiagStep(
                    id='root_exists',
                    title='Путь существует',
                    status='fail',
                    detail=f'Путь «{root}» не найден. Проверьте корневой путь в Admin и доступ аккаунта.',
                    duration_ms=ms,
                )
            )
            chain_ok = False

        if not chain_ok:
            report.add(
                DiagStep(
                    id='root_is_dir',
                    title='Путь — папка',
                    status='skip',
                    detail='Пропущено: путь недоступен.',
                )
            )
            report.add(
                DiagStep(
                    id='shallow_list',
                    title='Содержимое верхнего уровня',
                    status='skip',
                    detail='Пропущено.',
                )
            )
        else:

            def _meta():
                return ya_disk.get_meta(root)

            meta, ms, err = _timed(_meta)
            if err is not None:
                report.add(
                    DiagStep(
                        id='root_is_dir',
                        title='Путь — папка',
                        status='fail',
                        detail=f'Ошибка get_meta: {err}',
                        duration_ms=ms,
                    )
                )
                chain_ok = False
            elif getattr(meta, 'type', None) == 'dir':
                report.add(
                    DiagStep(
                        id='root_is_dir',
                        title='Путь — папка',
                        status='ok',
                        detail=f'«{root}» — каталог.',
                        duration_ms=ms,
                    )
                )
            else:
                report.add(
                    DiagStep(
                        id='root_is_dir',
                        title='Путь — папка',
                        status='fail',
                        detail=f'«{root}» не является папкой (type={getattr(meta, "type", "?")}).',
                        duration_ms=ms,
                    )
                )
                chain_ok = False

            if not chain_ok:
                report.add(
                    DiagStep(
                        id='shallow_list',
                        title='Содержимое верхнего уровня',
                        status='skip',
                        detail='Пропущено.',
                    )
                )
            else:

                def _list():
                    return list(ya_disk.listdir(root, limit=list_limit, offset=0))

                items, ms, err = _timed(_list)
                if err is not None:
                    report.add(
                        DiagStep(
                            id='shallow_list',
                            title='Содержимое верхнего уровня',
                            status='fail',
                            detail=f'Ошибка listdir: {err}',
                            duration_ms=ms,
                        )
                    )
                    chain_ok = False
                else:
                    assert items is not None
                    dirs = [i for i in items if getattr(i, 'type', None) == 'dir']
                    files = [i for i in items if getattr(i, 'type', None) != 'dir']
                    plx = [
                        i
                        for i in files
                        if (getattr(i, 'name', '') or '').lower().endswith('.plx')
                    ]
                    examples = [getattr(i, 'name', '?') for i in items[:5]]
                    example_txt = ', '.join(examples) if examples else '—'
                    truncated = len(items) >= list_limit
                    detail = (
                        f'Показано до {list_limit} элементов верхнего уровня (без рекурсии): '
                        f'папок {len(dirs)}, файлов {len(files)}, из них .plx {len(plx)}. '
                        f'Примеры: {example_txt}.'
                    )
                    if truncated:
                        detail += ' Список обрезан по лимиту.'
                    if len(plx) == 0 and len(dirs) > 0:
                        status = 'warn'
                        detail += (
                            ' На верхнем уровне нет .plx, но есть подпапки — '
                            'файлы могут лежать глубже; полная синхронизация обойдёт их рекурсивно.'
                        )
                    elif len(items) == 0:
                        status = 'warn'
                        detail += ' Папка пуста.'
                    else:
                        status = 'ok'
                    report.add(
                        DiagStep(
                            id='shallow_list',
                            title='Содержимое верхнего уровня',
                            status=status,
                            detail=detail,
                            duration_ms=ms,
                        )
                    )

    # --- write_probe ---
    if connection.write_mode != WriteMode.READ_WRITE:
        report.add(
            DiagStep(
                id='write_probe',
                title='Пробная запись',
                status='skip',
                detail='Пропущено: подключение только для чтения.',
            )
        )
    elif not chain_ok or ya_disk is None:
        report.add(
            DiagStep(
                id='write_probe',
                title='Пробная запись',
                status='skip',
                detail='Пропущено: нет рабочей авторизации или пути.',
            )
        )
    else:
        probe_remote = root.rstrip('/') + '/' + PROBE_FILENAME if root != '/' else '/' + PROBE_FILENAME

        def _probe():
            with tempfile.NamedTemporaryFile(suffix='.tmp', delete=False) as tmp:
                tmp.write(b'plx-diag-probe')
                local = tmp.name
            try:
                ya_disk.upload(local, probe_remote, overwrite=True)
                if ya_disk.exists(probe_remote):
                    ya_disk.remove(probe_remote, permanently=True)
            finally:
                Path(local).unlink(missing_ok=True)

        _, ms, err = _timed(_probe)
        if err is not None:
            report.add(
                DiagStep(
                    id='write_probe',
                    title='Пробная запись',
                    status='fail',
                    detail=f'Не удалось записать/удалить пробный файл: {err}',
                    duration_ms=ms,
                )
            )
        else:
            report.add(
                DiagStep(
                    id='write_probe',
                    title='Пробная запись',
                    status='ok',
                    detail=f'Файл «{PROBE_FILENAME}» успешно создан и удалён в «{root}».',
                    duration_ms=ms,
                )
            )

    statuses = {s.status for s in report.steps}
    if 'fail' in statuses:
        report.verdict = 'failed'
    elif 'warn' in statuses:
        report.verdict = 'degraded'
    else:
        report.verdict = 'ok'
    return report


VERDICT_LABELS = {
    'ok': 'Всё в порядке',
    'degraded': 'Есть предупреждения',
    'failed': 'Есть ошибки',
}
