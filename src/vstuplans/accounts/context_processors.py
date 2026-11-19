"""Контекстные процессоры: роль, брендинг, навигация."""
from __future__ import annotations

from django.conf import settings
from django.http import HttpRequest

from accounts.permissions import (
    primary_role_display,
    user_can_hard_delete,
    user_can_manage_feedback,
    user_can_manage_sync,
    user_can_upload,
    user_roles,
)
from accounts.roles import Role


def role_context(request: HttpRequest) -> dict:
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {'user_role_label': '', 'user_roles': frozenset()}
    return {
        'user_role_label': primary_role_display(request.user.pk),
        'user_roles': user_roles(request.user.pk),
    }


def branding_context(request: HttpRequest) -> dict:
    branding = getattr(settings, 'BRANDING', {})
    return {
        'branding': branding,
        'admin_url_path': getattr(settings, 'ADMIN_URL_PATH', 'admin/'),
    }


def nav_context(request: HttpRequest) -> dict:
    user = getattr(request, 'user', None)
    authenticated = bool(user and user.is_authenticated)
    roles = user_roles(user.pk) if authenticated else frozenset()
    is_admin = Role.ADMINISTRATOR in roles or (authenticated and user.is_superuser)
    return {
        'nav_can_upload': authenticated and user_can_upload(user.pk),
        'nav_can_manage_sync': authenticated and user_can_manage_sync(user.pk),
        'nav_can_manage_feedback': authenticated and user_can_manage_feedback(user.pk),
        'nav_can_hard_delete': authenticated and user_can_hard_delete(user.pk),
        'nav_is_admin': is_admin,
        'nav_show_external_replicas': authenticated
        and bool(roles & {Role.MANAGER, Role.ADMINISTRATOR, Role.REVIEWER}),
    }
