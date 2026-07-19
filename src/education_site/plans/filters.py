import django_filters
from django.db.models import Q

from documents.models import DocumentVersion, VersionStatus


class PlxDocumentFilter(django_filters.FilterSet):
    status = django_filters.ChoiceFilter(
        choices=VersionStatus.choices,
        label='Статус',
    )
    faculty = django_filters.CharFilter(
        method='filter_faculty',
        label='Факультет',
    )
    department = django_filters.CharFilter(
        method='filter_department',
        label='Кафедра',
    )
    year_start = django_filters.NumberFilter(
        field_name='extracted_metadata__year_start',
        label='Год начала',
    )
    direction_code = django_filters.CharFilter(
        field_name='extracted_metadata__direction_code',
        lookup_expr='icontains',
        label='Код направления',
    )
    profile = django_filters.CharFilter(
        field_name='extracted_metadata__profile',
        lookup_expr='icontains',
        label='Профиль',
    )
    q = django_filters.CharFilter(method='filter_q', label='Поиск')

    class Meta:
        model = DocumentVersion
        fields = []

    def filter_faculty(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(extracted_metadata__faculty_abbr_ru__icontains=value)
            | Q(extracted_metadata__faculty__icontains=value)
        )

    def filter_department(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(extracted_metadata__department_abbr_ru__icontains=value)
            | Q(extracted_metadata__department__icontains=value)
        )

    def filter_q(self, queryset, name, value):
        if not value:
            return queryset
        return queryset.filter(
            Q(storage_key__icontains=value)
            | Q(extracted_metadata__direction__icontains=value)
            | Q(extracted_metadata__profile__icontains=value)
            | Q(extracted_metadata__faculty__icontains=value)
            | Q(extracted_metadata__faculty_abbr_ru__icontains=value)
            | Q(extracted_metadata__department__icontains=value)
            | Q(extracted_metadata__department_abbr_ru__icontains=value)
        )
