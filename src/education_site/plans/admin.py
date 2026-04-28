from django.contrib import admin
from django.contrib.auth.models import User, Group
from .models import EducationalPlan

# Убираем Users и Groups из админки
admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(EducationalPlan)
class EducationalPlanAdmin(admin.ModelAdmin):
    list_display = ['source_path', 'direction_code', 'direction', 'faculty', 'department', 'year_start', 'status', 'created_at']
    list_filter = ['faculty', 'status', 'year_start']
    search_fields = ['source_path', 'direction', 'direction_code', 'faculty', 'department']

    def save_model(self, request, obj, form, change):
        if obj.source_path and not obj.direction:
            obj.parse_source_path()
        super().save_model(request, obj, form, change)