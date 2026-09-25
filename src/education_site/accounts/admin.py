from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group, User

from accounts.roles import ROLE_DISPLAY_NAMES, Role


# Свободной регистрации нет: учётные записи создаёт только администратор
# (Admin → Пользователи или createsuperuser).

admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = DjangoUserAdmin.list_display + ('role_labels',)
    filter_horizontal = ('groups', 'user_permissions')

    @admin.display(description='Роли')
    def role_labels(self, obj: User) -> str:
        known = {r.value: ROLE_DISPLAY_NAMES[r] for r in Role}
        labels = [
            known[name]
            for name in obj.groups.values_list('name', flat=True)
            if name in known
        ]
        if obj.is_superuser and ROLE_DISPLAY_NAMES[Role.ADMINISTRATOR] not in labels:
            labels.insert(0, ROLE_DISPLAY_NAMES[Role.ADMINISTRATOR])
        return ', '.join(labels) or '—'


@admin.register(Group)
class RoleGroupAdmin(GroupAdmin):
    """Группы ролей видны в админке; имена групп-ролей не удалять."""

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.name in {r.value for r in Role}:
            return False
        return super().has_delete_permission(request, obj)
