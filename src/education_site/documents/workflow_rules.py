from __future__ import annotations

from dataclasses import dataclass

from .entities import VersionStatus, WorkflowAction


@dataclass(frozen=True)
class TransitionRule:
    from_status: VersionStatus
    to_status: VersionStatus
    action: WorkflowAction
    requires_comment: bool = False


# Central table for workflow behavior and UI/action contract.
TRANSITION_RULES: tuple[TransitionRule, ...] = (
    TransitionRule(
        from_status=VersionStatus.NEW,
        to_status=VersionStatus.ON_REVIEW,
        action=WorkflowAction.SUBMIT,
        requires_comment=False,
    ),
    TransitionRule(
        from_status=VersionStatus.ON_REVIEW,
        to_status=VersionStatus.NEEDS_FIX,
        action=WorkflowAction.REQUEST_FIX,
        requires_comment=True,
    ),
    TransitionRule(
        from_status=VersionStatus.NEEDS_FIX,
        to_status=VersionStatus.ON_REVIEW,
        action=WorkflowAction.RESUBMIT,
        requires_comment=False,
    ),
    TransitionRule(
        from_status=VersionStatus.ON_REVIEW,
        to_status=VersionStatus.APPROVED,
        action=WorkflowAction.APPROVE,
        requires_comment=False,
    ),
    TransitionRule(
        from_status=VersionStatus.APPROVED,
        to_status=VersionStatus.ARCHIVED,
        action=WorkflowAction.ARCHIVE,
        requires_comment=False,
    ),
    TransitionRule(
        from_status=VersionStatus.NEW,
        to_status=VersionStatus.TRASHED,
        action=WorkflowAction.MOVE_TO_TRASH,
        requires_comment=False,
    ),
    TransitionRule(
        from_status=VersionStatus.ON_REVIEW,
        to_status=VersionStatus.TRASHED,
        action=WorkflowAction.MOVE_TO_TRASH,
        requires_comment=False,
    ),
    TransitionRule(
        from_status=VersionStatus.NEEDS_FIX,
        to_status=VersionStatus.TRASHED,
        action=WorkflowAction.MOVE_TO_TRASH,
        requires_comment=False,
    ),
    TransitionRule(
        from_status=VersionStatus.APPROVED,
        to_status=VersionStatus.TRASHED,
        action=WorkflowAction.MOVE_TO_TRASH,
        requires_comment=False,
    ),
    TransitionRule(
        from_status=VersionStatus.ARCHIVED,
        to_status=VersionStatus.TRASHED,
        action=WorkflowAction.MOVE_TO_TRASH,
        requires_comment=False,
    ),
    TransitionRule(
        from_status=VersionStatus.INVALID,
        to_status=VersionStatus.TRASHED,
        action=WorkflowAction.MOVE_TO_TRASH,
        requires_comment=False,
    ),
    TransitionRule(
        from_status=VersionStatus.TRASHED,
        to_status=VersionStatus.NEW,
        action=WorkflowAction.RESTORE,
        requires_comment=False,
    ),
)


def get_rule(from_status: VersionStatus, to_status: VersionStatus) -> TransitionRule | None:
    for rule in TRANSITION_RULES:
        if rule.from_status == from_status and rule.to_status == to_status:
            return rule
    return None


def can_transition(from_status: VersionStatus, to_status: VersionStatus) -> bool:
    return get_rule(from_status, to_status) is not None

