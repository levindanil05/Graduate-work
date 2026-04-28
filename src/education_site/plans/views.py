from django.shortcuts import render, redirect
from .models import EducationalPlan

def plan_list(request):
    """Отображает список всех учебных планов"""
    plans = EducationalPlan.objects.all().order_by('direction_code', 'year_start', 'source_path')
    return render(request, 'plans/plan_list.html', {'plans': plans})

def plan_add(request):
    """Добавление нового плана (через админку)"""
    return redirect('admin:plans_educationalplan_changelist')