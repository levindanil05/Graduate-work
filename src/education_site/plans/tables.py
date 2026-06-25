import django_tables2 as tables

from .models import EducationalPlan


class EducationalPlanTable(tables.Table):
    source_path = tables.Column(verbose_name='Файл')
    direction_code = tables.Column(verbose_name='Код направления')
    direction = tables.Column(verbose_name='Направление')
    faculty = tables.Column(verbose_name='Факультет')
    department = tables.Column(verbose_name='Кафедра')
    year_start = tables.Column(verbose_name='Год')
    qualification = tables.Column(verbose_name='Квалификация')
    status = tables.Column(
        verbose_name='Статус',
        accessor='get_status_display',
        order_by='status',
    )
    updated_at = tables.DateTimeColumn(verbose_name='Обновлён', format='d.m.Y H:i')

    class Meta:
        model = EducationalPlan
        fields = (
            'source_path',
            'direction_code',
            'direction',
            'faculty',
            'department',
            'year_start',
            'qualification',
            'status',
            'updated_at',
        )
