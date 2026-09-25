from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from accounts.roles import (
    ROLE_CAN_EDIT_DOCUMENT,
    ROLE_CAN_HARD_DELETE,
    ROLE_CAN_MANAGE_SYNC,
    ROLE_CAN_UPLOAD,
    ROLE_DISPLAY_NAMES,
    ROLE_WORKFLOW_ACTIONS,
    SYSTEM_ACTOR_USER_ID,
    Role,
)
from documents.entities import Document, DocumentVersion, VersionStatus
from documents.workflow_rules import get_rule


def ensure_role_groups() -> None:
    for role in Role:
        Group.objects.get_or_create(name=role.value)


def user_roles(user_id: int | None) -> frozenset[Role]:
    if user_id is None or user_id == SYSTEM_ACTOR_USER_ID:
        return frozenset({Role.ADMINISTRATOR})

    User = get_user_model()
    try:
        user = User.objects.prefetch_related('groups').get(pk=user_id)
    except User.DoesNotExist:
        return frozenset()

    if user.is_superuser:
        return frozenset({Role.ADMINISTRATOR})

    known = {r.value for r in Role}
    roles: set[Role] = set()
    for name in user.groups.values_list('name', flat=True):
        if name in known:
            roles.add(Role(name))
    return frozenset(roles)


def primary_role_display(user_id: int | None) -> str:
    roles = user_roles(user_id)
    if not roles:
        return 'Без роли'
    order = (
        Role.ADMINISTRATOR,
        Role.MANAGER,
        Role.REVIEWER,
        Role.CURRICULUM_DEVELOPER,
        Role.READER,
    )
    for role in order:
        if role in roles:
            return ROLE_DISPLAY_NAMES[role]
    return ROLE_DISPLAY_NAMES[next(iter(roles))]


def _has_any(roles: frozenset[Role], allowed: frozenset[Role]) -> bool:
    return bool(roles & allowed)


class RolePermissionService:
    """Проверка прав по ролям Django Group (planing §10.13)."""

    def can_upload_version(self, user_id: int, document: Document) -> bool:
        return _has_any(user_roles(user_id), ROLE_CAN_UPLOAD)

    def can_transition(
        self, user_id: int, version: DocumentVersion, to_status: VersionStatus
    ) -> bool:
        roles = user_roles(user_id)
        if Role.ADMINISTRATOR in roles:
            return True
        rule = get_rule(version.status, to_status)
        if rule is None:
            return False
        allowed_actions = frozenset().union(
            *(ROLE_WORKFLOW_ACTIONS.get(role, frozenset()) for role in roles)
        )
        return rule.action in allowed_actions

    def can_trash(self, user_id: int, document: Document) -> bool:
        roles = user_roles(user_id)
        if Role.ADMINISTRATOR in roles:
            return True
        allowed = frozenset(
            {
                Role.CURRICULUM_DEVELOPER,
                Role.REVIEWER,
                Role.MANAGER,
                Role.ADMINISTRATOR,
            }
        )
        return _has_any(roles, allowed)

    def can_restore(self, user_id: int, document: Document) -> bool:
        return self.can_trash(user_id, document)

    def can_hard_delete(self, user_id: int, document: Document) -> bool:
        return _has_any(user_roles(user_id), ROLE_CAN_HARD_DELETE)

    def can_edit_document(self, user_id: int, document: Document | None = None) -> bool:
        return _has_any(user_roles(user_id), ROLE_CAN_EDIT_DOCUMENT)

    def can_manage_sync(self, user_id: int) -> bool:
        return _has_any(user_roles(user_id), ROLE_CAN_MANAGE_SYNC)
