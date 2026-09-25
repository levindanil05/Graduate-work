"""Роли пользователей (Django Groups) и матрица прав по planing-2605010 §10.13.

Управляющий: как рецензент + синхронизация внешних хранилищ;
без управления пользователями и без физического удаления.
"""
from __future__ import annotations

from enum import StrEnum

from documents.entities import VersionStatus, WorkflowAction


class Role(StrEnum):
    READER = 'reader'
    CURRICULUM_DEVELOPER = 'curriculum_developer'
    REVIEWER = 'reviewer'
    MANAGER = 'manager'
    ADMINISTRATOR = 'administrator'


ROLE_DISPLAY_NAMES: dict[Role, str] = {
    Role.READER: 'Читатель',
    Role.CURRICULUM_DEVELOPER: 'Разработчик УП (кафедра)',
    Role.REVIEWER: 'Рецензент (учебный отдел)',
    Role.MANAGER: 'Управляющий',
    Role.ADMINISTRATOR: 'Администратор',
}

# Действия workflow, разрешённые роли (без учёта текущего статуса — статус проверяет get_rule).
ROLE_WORKFLOW_ACTIONS: dict[Role, frozenset[WorkflowAction]] = {
    Role.READER: frozenset(),
    Role.CURRICULUM_DEVELOPER: frozenset(
        {
            WorkflowAction.SUBMIT,
            WorkflowAction.RESUBMIT,
            WorkflowAction.MOVE_TO_TRASH,
            WorkflowAction.RESTORE,
        }
    ),
    Role.REVIEWER: frozenset(
        {
            WorkflowAction.REQUEST_FIX,
            WorkflowAction.APPROVE,
            WorkflowAction.MOVE_TO_TRASH,
            WorkflowAction.RESTORE,
        }
    ),
    Role.MANAGER: frozenset(
        {
            WorkflowAction.REQUEST_FIX,
            WorkflowAction.APPROVE,
            WorkflowAction.MOVE_TO_TRASH,
            WorkflowAction.RESTORE,
        }
    ),
    Role.ADMINISTRATOR: frozenset(WorkflowAction),
}

ROLE_CAN_UPLOAD: frozenset[Role] = frozenset(
    {Role.CURRICULUM_DEVELOPER, Role.ADMINISTRATOR}
)
ROLE_CAN_EDIT_DOCUMENT: frozenset[Role] = frozenset(
    {
        Role.CURRICULUM_DEVELOPER,
        Role.REVIEWER,
        Role.MANAGER,
        Role.ADMINISTRATOR,
    }
)
ROLE_CAN_MANAGE_SYNC: frozenset[Role] = frozenset({Role.MANAGER, Role.ADMINISTRATOR})
ROLE_CAN_HARD_DELETE: frozenset[Role] = frozenset({Role.ADMINISTRATOR})

# Системный актор синхронизации (documents.services.SYNC_ACTOR_USER_ID).
SYSTEM_ACTOR_USER_ID = 0
