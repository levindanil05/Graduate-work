from __future__ import annotations

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy

from documents.entities import DocumentVersion, VersionStatus, WorkflowAction
from documents.lifecycle import (
    action_label_for_type,
    get_rule_for_type,
    list_rules_for_type,
    status_label_for_type,
)
from documents.workflow_rules import TransitionRule


_ACTION_LABELS: dict[WorkflowAction, str] = {
    WorkflowAction.SUBMIT: _lazy('Submit for review'),
    WorkflowAction.REQUEST_FIX: _lazy('Request fix'),
    WorkflowAction.RESUBMIT: _lazy('Resubmit for review'),
    WorkflowAction.AGREE: _lazy('Agree (academic office)'),
    WorkflowAction.APPROVE: _lazy('Approve (printed form received)'),
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


def list_allowed_transitions(
    from_status: str | VersionStatus,
    *,
    document_type: str | None = None,
) -> list[TransitionRule]:
    try:
        status = _to_domain_status(from_status)
    except ValueError:
        # Неизвестный код статуса — только системные правила через list_rules_for_type.
        return list_rules_for_type(str(from_status), document_type=document_type)
    return list_rules_for_type(status, document_type=document_type)


def list_allowed_transitions_for_user(
    from_status: str | VersionStatus,
    *,
    user_id: int | None,
    version: DocumentVersion | None = None,
    document_type: str | None = None,
) -> list[TransitionRule]:
    """Переходы, разрешённые и статусом, и ролью пользователя."""
    doc_type = document_type
    if doc_type is None and version is not None and version.document_id:
        from documents.models import Document as OrmDocument

        doc_type = (
            OrmDocument.objects.filter(pk=version.document_id)
            .values_list('document_type', flat=True)
            .first()
        )
    rules = list_allowed_transitions(from_status, document_type=doc_type)
    if user_id is None:
        return []
    from accounts.permissions import RolePermissionService

    perms = RolePermissionService()
    if version is None:
        try:
            version = DocumentVersion(status=_to_domain_status(from_status))
        except ValueError:
            version = DocumentVersion(status=VersionStatus.NEW)
    return [
        rule
        for rule in rules
        if perms.can_transition(user_id, version, rule.to_status, document_type=doc_type)
    ]


def transition_label(rule: TransitionRule, *, document_type: str | None = None) -> str:
    if rule.action_label_override:
        return rule.action_label_override
    override = action_label_for_type(rule.action, document_type)
    if override:
        return override
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


def target_status_label(
    status: str | VersionStatus,
    *,
    document_type: str | None = None,
) -> str:
    return status_label_for_type(status, document_type)


def has_allowed_transitions(
    from_status: str | VersionStatus,
    *,
    document_type: str | None = None,
) -> bool:
    return bool(list_allowed_transitions(from_status, document_type=document_type))
