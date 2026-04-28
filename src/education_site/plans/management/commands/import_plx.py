import os
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from plans.models import EducationalPlan
from plx_parser import parse_plx_file


class Command(BaseCommand):
    help = "Импортирует все .plx из userfiles в БД (сохраняются только метаданные и source_path)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            type=str,
            default=str(getattr(settings, "USERFILES_ROOT", "")),
            help="Корневая папка userfiles (по умолчанию settings.USERFILES_ROOT)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только показать, что будет импортировано (без записи в БД)",
        )

    def handle(self, *args, **options):
        root = Path(options["path"]).resolve()
        dry_run = bool(options["dry_run"])

        if not root.exists() or not root.is_dir():
            self.stderr.write(self.style.ERROR(f"Папка не найдена: {root}"))
            return

        created = 0
        updated = 0
        failed = 0
        scanned = 0
        failures = []

        for dirpath, _, filenames in os.walk(root):
            for filename in filenames:
                if not filename.lower().endswith(".plx"):
                    continue

                scanned += 1
                abs_path = Path(dirpath) / filename
                rel_path = abs_path.relative_to(root).as_posix()

                data = parse_plx_file(str(abs_path))
                if data.get("error"):
                    failed += 1
                    failures.append((rel_path, data.get("error", "")))
                    continue

                defaults = {
                    "direction_code": data.get("direction_code", ""),
                    "direction": data.get("direction", ""),
                    "faculty": data.get("faculty", ""),
                    "department": data.get("department", ""),
                    "qualification": data.get("qualification", ""),
                    "year_start": int(data["year_start"]) if str(data.get("year_start", "")).isdigit() else None,
                }

                if dry_run:
                    self.stdout.write(f"[DRY] {rel_path} -> {defaults.get('direction_code','')} {defaults.get('direction','')}")
                    continue

                obj, was_created = EducationalPlan.objects.update_or_create(
                    source_path=rel_path,
                    defaults=defaults,
                )
                if was_created:
                    created += 1
                else:
                    updated += 1

        self.stdout.write(self.style.SUCCESS(f"Сканировано файлов: {scanned}"))
        self.stdout.write(self.style.SUCCESS(f"Создано: {created}"))
        self.stdout.write(self.style.SUCCESS(f"Обновлено: {updated}"))
        self.stdout.write(self.style.WARNING(f"Ошибок: {failed}"))

        if failures:
            self.stdout.write("")
            self.stdout.write("Файлы с ошибками парсинга:")
            for rel_path, err in failures[:50]:
                self.stdout.write(f"- {rel_path}: {err}")
            if len(failures) > 50:
                self.stdout.write(f"... и ещё {len(failures) - 50}")

