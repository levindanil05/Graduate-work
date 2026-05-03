# plans/management/commands/update_from_yandex.py
import os
import tempfile
import shutil
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from plans.yandex_client import get_yandex_client, list_plx_files, download_plx_file
from plans.plx_parser import parse_plx_file
from plans.models import EducationalPlan

# Словарь для преобразования числовой квалификации в текст
QUALIFICATION_MAP = {
    '1': 'Бакалавриат',
    '2': 'Магистратура',
    '3': 'Специалитет',
}

def normalize_qualification(value):
    """Если значение — цифра 1,2,3, заменяем на русский текст, иначе оставляем как есть."""
    if value and value.strip() in QUALIFICATION_MAP:
        return QUALIFICATION_MAP[value.strip()]
    return value

class Command(BaseCommand):
    help = 'Скачивает все PLX с Яндекс.Диска, парсит и обновляет БД'

    def handle(self, *args, **options):
        disk = get_yandex_client()
        if not disk.check_token():
            self.stdout.write(self.style.ERROR('❌ Неверный токен Яндекс.Диска'))
            return

        plx_files = list_plx_files(disk, settings.YANDEX_DISK_BASE_PATH)
        self.stdout.write(f'📁 Найдено PLX-файлов: {len(plx_files)}')

        userfiles_root = Path(settings.USERFILES_ROOT)
        userfiles_root.mkdir(parents=True, exist_ok=True)

        created = 0
        updated = 0
        errors = 0

        for remote_file in plx_files:
            # Формируем относительный путь для сохранения:
            # отрезаем базовый путь YANDEX_DISK_BASE_PATH и сохраняем структуру папок
            rel_path = str(remote_file.path)
            if rel_path.startswith(settings.YANDEX_DISK_BASE_PATH.rstrip('/')):
                rel_path = rel_path[len(settings.YANDEX_DISK_BASE_PATH.rstrip('/')):].lstrip('/')
            # Заменяем недопустимые символы в Windows (оставляем только папки и имя файла)
            safe_rel_path = rel_path.replace('/', os.sep)
            local_path = userfiles_root / safe_rel_path

            # Скачиваем во временную папку, потом перемещаем на место
            with tempfile.NamedTemporaryFile(suffix='.plx', delete=False) as tmp_file:
                tmp_path = tmp_file.name
            try:
                download_plx_file(disk, remote_file.path, tmp_path)

                # Парсим метаданные
                data = parse_plx_file(tmp_path)
                if data.get('error'):
                    self.stderr.write(f'⚠️ Ошибка парсинга {remote_file.name}: {data["error"]}')
                    errors += 1
                    continue

                # Нормализуем квалификацию
                qual = normalize_qualification(data.get('qualification', ''))

                # Год начала подготовки: может быть строкой, преобразуем в int
                year_str = data.get('year_start', '')
                year = int(year_str) if year_str and year_str.isdigit() else None

                # Создаём или обновляем запись в БД
                obj, is_created = EducationalPlan.objects.update_or_create(
                    source_path=safe_rel_path,   # уникальный идентификатор
                    defaults={
                        'direction_code': data.get('direction_code', ''),
                        'direction': data.get('direction', ''),
                        'faculty': data.get('faculty', ''),
                        'department': data.get('department', ''),
                        'year_start': year,
                        'qualification': qual,
                        # comments и status не трогаем, оставляем старые значения
                    }
                )

                # Копируем временный файл в нужное место (перезаписывая, если есть)
                local_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(tmp_path, local_path)

                if is_created:
                    created += 1
                else:
                    updated += 1

                self.stdout.write(f'{"✅ Создан" if is_created else "🔄 Обновлён"} {safe_rel_path}')

            except Exception as e:
                self.stderr.write(f'❌ Ошибка обработки {remote_file.name}: {e}')
                errors += 1
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        self.stdout.write(self.style.SUCCESS(
            f'\n✨ Готово: создано {created}, обновлено {updated}, ошибок {errors}'
        ))