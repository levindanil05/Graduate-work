from django.contrib import admin
from django.contrib.auth.models import User, Group
from .models import EducationalPlan

# Убираем Users и Groups из админки
admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(EducationalPlan)
class EducationalPlanAdmin(admin.ModelAdmin):
    list_display = ['direction_code', 'direction', 'faculty', 'department', 'year_start', 'status', 'created_at']
    list_filter = ['faculty', 'status', 'year_start']
    search_fields = ['direction', 'direction_code', 'faculty', 'department']

    def save_model(self, request, obj, form, change):
        # Если файл загружен и поля пустые - парсим
        if obj.file and not obj.direction:
            obj.parse_file()
        super().save_model(request, obj, form, change)