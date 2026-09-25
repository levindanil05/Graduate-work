from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import User

from accounts.roles import ROLE_DISPLAY_NAMES, Role


admin.site.unregister(User)


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = DjangoUserAdmin.list_display + ('role_labels',)
    filter_horizontal = ('groups', 'user_permissions')

    @admin.display(description='Роли')
    def role_labels(self, obj: User) -> str:
        known = {r.value: ROLE_DISPLAY_NAMES[r] for r in Role}
        labels = [known[name] for name in obj.groups.values_list('name', flat=True) if name in known]
        if obj.is_superuser and ROLE_DISPLAY_NAMES[Role.ADMINISTRATOR] not in labels:
            labels.insert(0, ROLE_DISPLAY_NAMES[Role.ADMINISTRATOR])
        return ', '.join(labels) or '—'
