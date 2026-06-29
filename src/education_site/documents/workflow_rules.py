from __future__ import annotations

from dataclasses import dataclass

from .entities import VersionStatus, WorkflowAction

# Special source marker for rules that apply to any current status.
ANY_STATUS = "*"


@dataclass(frozen=True)
class TransitionRule:
    from_status: VersionStatus | str
    to_status: VersionStatus
    action: WorkflowAction
    requires_comment: bool = False
    # Optional guard for "ANY" rules.
    exclude_from: tuple[VersionStatus, ...] = ()


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
    # Universal rule: any non-trashed version can be moved to trash.
    TransitionRule(
        from_status=ANY_STATUS,
        to_status=VersionStatus.TRASHED,
        action=WorkflowAction.MOVE_TO_TRASH,
        requires_comment=False,
        exclude_from=(VersionStatus.TRASHED,),
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
        if rule.to_status != to_status:
            continue
        if rule.from_status == from_status:
            return rule
        if rule.from_status == ANY_STATUS and from_status not in rule.exclude_from:
            return rule
    return None


def can_transition(from_status: VersionStatus, to_status: VersionStatus) -> bool:
    return get_rule(from_status, to_status) is not None


def list_rules_from(from_status: VersionStatus) -> list[TransitionRule]:
    """Return all transition rules available from the given status."""
    rules: list[TransitionRule] = []
    seen_targets: set[VersionStatus] = set()
    for rule in TRANSITION_RULES:
        matches = rule.from_status == from_status or (
            rule.from_status == ANY_STATUS and from_status not in rule.exclude_from
        )
        if matches and rule.to_status not in seen_targets:
            rules.append(rule)
            seen_targets.add(rule.to_status)
    return rules

