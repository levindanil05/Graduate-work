from __future__ import annotations

from documents.entities import VersionStatus, WorkflowAction
from documents.models import VersionStatus as OrmVersionStatus
from documents.workflow_rules import TransitionRule, list_rules_from


_ACTION_LABELS: dict[WorkflowAction, str] = {
    WorkflowAction.SUBMIT: 'Отправить на проверку',
    WorkflowAction.REQUEST_FIX: 'Отправить на доработку',
    WorkflowAction.RESUBMIT: 'Повторно отправить на проверку',
    WorkflowAction.APPROVE: 'Утвердить',
    WorkflowAction.ARCHIVE: 'В архив',
    WorkflowAction.MARK_INVALID: 'Пометить невалидным',
    WorkflowAction.MOVE_TO_TRASH: 'В корзину',
    WorkflowAction.RESTORE: 'Восстановить',
    WorkflowAction.HARD_DELETE: 'Удалить физически',
}

_ACTION_LABELS_BY_VALUE: dict[str, str] = {
    action.value: label for action, label in _ACTION_LABELS.items()
}


def _to_domain_status(status: str | VersionStatus) -> VersionStatus:
    if isinstance(status, VersionStatus):
        return status
    return VersionStatus(status)


def list_allowed_transitions(from_status: str | VersionStatus) -> list[TransitionRule]:
    return list_rules_from(_to_domain_status(from_status))


def transition_label(rule: TransitionRule) -> str:
    return action_label(rule.action)


def action_label(action: str | WorkflowAction) -> str:
    if isinstance(action, WorkflowAction):
        return _ACTION_LABELS.get(action, action.value)
    return _ACTION_LABELS_BY_VALUE.get(action, action)


def target_status_label(status: str | VersionStatus) -> str:
    key = status.value if isinstance(status, VersionStatus) else status
    return dict(OrmVersionStatus.choices).get(key, key)


def has_allowed_transitions(from_status: str | VersionStatus) -> bool:
    return bool(list_allowed_transitions(from_status))
