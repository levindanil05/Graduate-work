from __future__ import annotations

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest

from accounts.permissions import RolePermissionService, user_roles
from accounts.roles import ROLE_CAN_MANAGE_SYNC, ROLE_CAN_UPLOAD, Role


def _user_id(request: HttpRequest) -> int | None:
    if not request.user.is_authenticated:
        return None
    return request.user.pk


def user_has_role(request: HttpRequest, *roles: Role) -> bool:
    uid = _user_id(request)
    if uid is None:
        return False
    return bool(user_roles(uid) & frozenset(roles))


def user_can_upload(request: HttpRequest) -> bool:
    uid = _user_id(request)
    if uid is None:
        return False
    return bool(user_roles(uid) & ROLE_CAN_UPLOAD)


def user_can_manage_sync(request: HttpRequest) -> bool:
    uid = _user_id(request)
    if uid is None:
        return False
    return RolePermissionService().can_manage_sync(uid)


def user_can_edit_document(request: HttpRequest) -> bool:
    uid = _user_id(request)
    if uid is None:
        return False
    return RolePermissionService().can_edit_document(uid)


def role_required(*roles: Role):
    """Decorator: login + at least one of the given roles (or administrator)."""

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if user_has_role(request, Role.ADMINISTRATOR, *roles):
                return view_func(request, *args, **kwargs)
            raise PermissionDenied('Недостаточно прав для этого действия')

        return _wrapped

    return decorator


def upload_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if user_can_upload(request) or user_has_role(request, Role.ADMINISTRATOR):
            return view_func(request, *args, **kwargs)
        raise PermissionDenied('Загрузка доступна разработчику УП или администратору')

    return _wrapped


def sync_required(view_func):
    @login_required
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if user_can_manage_sync(request):
            return view_func(request, *args, **kwargs)
        raise PermissionDenied('Синхронизация доступна управляющему или администратору')

    return _wrapped
