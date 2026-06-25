import django_filters
from django.db.models import Q

from .models import EducationalPlan


class EducationalPlanFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        choices=EducationalPlan._meta.get_field('status').choices,
        label='Статус',
    )
    faculty = django_filters.CharFilter(lookup_expr='icontains', label='Факультет')
    department = django_filters.CharFilter(lookup_expr='icontains', label='Кафедра')
    year_start = django_filters.NumberFilter(label='Год начала')
    direction_code = django_filters.CharFilter(lookup_expr='icontains', label='Код направления')
    q = django_filters.CharFilter(method='filter_q', label='Поиск')

    class Meta:
        model = EducationalPlan
        fields = []

    def filter_q(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(source_path__icontains=value)
            | Q(direction__icontains=value)
            | Q(faculty__icontains=value)
            | Q(department__icontains=value)
        )
