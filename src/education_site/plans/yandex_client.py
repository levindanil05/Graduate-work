# plans/yandex_client.py
import yadisk
from django.conf import settings

def get_yandex_client():
    return yadisk.YaDisk(token=settings.YANDEX_DISK_TOKEN)

def list_plx_files(disk, path='/'):
    """Рекурсивно обходит папку path и возвращает список объектов файлов .plx,
    игнорируя любые папки с названием 'Архив' (регистронезависимо)."""
    files = []
    try:
        for item in disk.listdir(path):
            if item.is_dir():
                # Пропускаем папки "Архив", "архив", "АРХИВ" и т.д.
                if item.name.lower() == 'архив':
                    continue
                files.extend(list_plx_files(disk, item.path))
            elif item.is_file() and item.name.lower().endswith('.plx'):
                files.append(item)
    except Exception as e:
        print(f"Ошибка при обходе {path}: {e}")
    return files

def download_plx_file(disk, remote_path, local_path):
    """Скачивает файл в указанное локальное место (перезаписывает)."""
    disk.download(remote_path, local_path)