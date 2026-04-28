import os
import sys
from pathlib import Path

from django.conf import settings
from django.db import models

# Добавляем корень проекта в путь для импорта plx_parser
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class EducationalPlan(models.Model):
    # Источник: реальный файл в userfiles (без копирования в MEDIA_ROOT)
    source_path = models.CharField(
        max_length=500,
        unique=True,
        verbose_name='Путь к исходному файлу (относительно userfiles)',
        blank=True,
        default='',
    )

    faculty = models.CharField(max_length=200, verbose_name='Факультет', blank=True)
    department = models.CharField(max_length=200, verbose_name='Кафедра', blank=True)
    direction = models.CharField(max_length=300, verbose_name='Направление подготовки', blank=True)
    direction_code = models.CharField(max_length=50, verbose_name='Код направления', blank=True)
    year_start = models.IntegerField(verbose_name='Год начала подготовки', null=True, blank=True)
    qualification = models.CharField(max_length=100, verbose_name='Квалификация', blank=True)
    comments = models.TextField(blank=True, null=True, verbose_name='Комментарии')
    status = models.CharField(
        max_length=50,
        choices=[
            ('draft', 'Черновик'),
            ('review', 'На проверке'),  # noqa: RUF001
            ('approved', 'Утверждён'),
            ('rejected', 'Отправлен на доработку'),
        ],
        default='draft',
        verbose_name='Статус'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Дата обновления')

    def __str__(self):
        return f"{self.direction_code} - {self.direction} ({self.year_start})"

    class Meta:
        verbose_name = 'Учебный план'
        verbose_name_plural = 'Учебные планы'

    def parse_source_path(self):
        """Парсит реальный файл из userfiles по `source_path` и заполняет поля"""
        from plx_parser import parse_plx_file

        if not self.source_path:
            return

        root = getattr(settings, "USERFILES_ROOT", None)
        if not root:
            return

        abs_path = Path(root) / self.source_path
        if not abs_path.exists():
            return

        data = parse_plx_file(str(abs_path))
        if data.get("error"):
            return

        self.direction_code = data.get('direction_code', '')
        self.direction = data.get('direction', '')
        self.faculty = data.get('faculty', '')
        self.department = data.get('department', '')
        self.year_start = int(data.get('year_start', 0)) if data.get('year_start') else None
        self.qualification = data.get('qualification', '')
