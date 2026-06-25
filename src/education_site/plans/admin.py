from django.contrib import admin
from django.contrib.auth.models import Group, User

# Убираем Users и Groups из админки
admin.site.unregister(User)
admin.site.unregister(Group)
