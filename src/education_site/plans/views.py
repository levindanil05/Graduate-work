from django.shortcuts import render, redirect
from .models import EducationalPlan
from django.contrib.admin.views.decorators import staff_member_required
from django.core.management import call_command
from django.contrib import messages

def plan_list(request):
    """Отображает список всех учебных планов"""
    plans = EducationalPlan.objects.all().order_by('direction_code', 'year_start', 'source_path')
    return render(request, 'plans/plan_list.html', {'plans': plans})

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