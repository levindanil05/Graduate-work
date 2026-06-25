from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.management import call_command
from django.shortcuts import redirect, render
from django_tables2 import RequestConfig

from .filters import EducationalPlanFilter
from .models import EducationalPlan
from .tables import EducationalPlanTable


def plan_list(request):
    """Отображает список всех учебных планов с фильтрацией и сортировкой."""
    queryset = EducationalPlan.objects.all()
    filter_set = EducationalPlanFilter(request.GET, queryset=queryset)
    table = EducationalPlanTable(filter_set.qs)
    RequestConfig(request, paginate=False).configure(table)
    return render(
        request,
        'plans/plan_list.html',
        {
            'filter': filter_set,
            'table': table,
        },
    )


def plan_add(request):
    """Добавление нового плана (через админку)"""
    return redirect('admin:plans_educationalplan_changelist')


@staff_member_required
def sync_yandex(request):
    if request.method == 'POST':
        try:
            call_command('update_from_yandex')
            messages.success(request, 'Синхронизация с Яндекс.Диском завершена')
        except Exception as e:
            messages.error(request, f'Ошибка: {e}')
    return redirect(request.META.get('HTTP_REFERER', '/'))
