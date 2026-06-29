from __future__ import annotations

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy

from documents.entities import VersionStatus, WorkflowAction
from documents.models import VersionStatus as OrmVersionStatus
from documents.workflow_rules import TransitionRule, list_rules_from


_ACTION_LABELS: dict[WorkflowAction, str] = {
    WorkflowAction.SUBMIT: _lazy('Submit for review'),
    WorkflowAction.REQUEST_FIX: _lazy('Request fix'),
    WorkflowAction.RESUBMIT: _lazy('Resubmit for review'),
    WorkflowAction.APPROVE: _lazy('Approve'),
    WorkflowAction.ARCHIVE: _lazy('Archive'),
    WorkflowAction.MARK_INVALID: _lazy('Mark invalid'),
    WorkflowAction.MOVE_TO_TRASH: _lazy('Move to trash'),
    WorkflowAction.RESTORE: _lazy('Restore'),
    WorkflowAction.HARD_DELETE: _lazy('Hard delete'),
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
        label = _ACTION_LABELS.get(action)
        return _(label) if label else action.value
    try:
        label = _ACTION_LABELS.get(WorkflowAction(action))
        return _(label) if label else action
    except ValueError:
        return action


def target_status_label(status: str | VersionStatus) -> str:
    key = status.value if isinstance(status, VersionStatus) else status
    return dict(OrmVersionStatus.choices).get(key, key)


def has_allowed_transitions(from_status: str | VersionStatus) -> bool:
    return bool(list_allowed_transitions(from_status))
