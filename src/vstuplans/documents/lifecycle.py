"""Профили жизненного цикла видов документов.

Рантайм читает профиль через поставщик. Эта версия — settings / встроенный
профиль учебного плана. Следующая версия подставит чтение из БД без смены
карточки и сервиса переходов.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from documents.entities import VersionStatus, WorkflowAction
from documents.workflow_rules import ANY_STATUS, TRANSITION_RULES, TransitionRule


@dataclass(frozen=True)
class LifecycleStatus:
    code: str
    label: str


@dataclass(frozen=True)
class LifecycleTransition:
    action: str
    label: str
    from_status: str
    to_status: str
    roles: tuple[str, ...]
    requires_comment: bool = False


@dataclass(frozen=True)
class LifecycleProfile:
    statuses: tuple[LifecycleStatus, ...]
    transitions: tuple[LifecycleTransition, ...]
    create_roles: frozenset[str]
    update_roles: frozenset[str]
    view_roles: frozenset[str]

    def status_label(self, code: str) -> str | None:
        key = str(code)
        for item in self.statuses:
            if item.code == key:
                return item.label
        return None

    def action_label(self, action: str) -> str | None:
        key = str(action)
        for item in self.transitions:
            if item.action == key:
                return item.label
        return None


# Системные действия: не входят в конструктор вида.
_SYSTEM_ACTIONS = frozenset(
    {
        WorkflowAction.MOVE_TO_TRASH,
        WorkflowAction.RESTORE,
        WorkflowAction.HARD_DELETE,
        WorkflowAction.MARK_INVALID,
        WorkflowAction.ARCHIVE,
    }
)


def _role_set(*codes: str) -> frozenset[str]:
    return frozenset(codes)


def build_plx_lifecycle_profile() -> LifecycleProfile:
    """Профиль учебного плана = нынешняя таблица переходов и роли по умолчанию."""
    from accounts.roles import ROLE_WORKFLOW_ACTIONS, Role

    statuses = (
        LifecycleStatus(VersionStatus.NEW.value, 'Новый'),
        LifecycleStatus(VersionStatus.ON_REVIEW.value, 'На проверке'),
        LifecycleStatus(VersionStatus.NEEDS_FIX.value, 'Требует доработки'),
        LifecycleStatus(VersionStatus.AGREED.value, 'Согласован УО'),
        LifecycleStatus(VersionStatus.APPROVED.value, 'Утверждён'),
        LifecycleStatus(VersionStatus.ARCHIVED.value, 'В архиве'),
        LifecycleStatus(VersionStatus.INVALID.value, 'Некорректный'),
        LifecycleStatus(VersionStatus.TRASHED.value, 'В корзине'),
    )

    transitions: list[LifecycleTransition] = []
    for rule in TRANSITION_RULES:
        if rule.action in (WorkflowAction.MOVE_TO_TRASH, WorkflowAction.RESTORE):
            continue
        if rule.from_status == ANY_STATUS:
            continue
        roles = tuple(
            sorted(
                role.value
                for role, actions in ROLE_WORKFLOW_ACTIONS.items()
                if rule.action in actions and role != Role.ADMINISTRATOR
            )
        )
        # Администратор всегда может; явно добавляем для ясности профиля.
        role_list = list(roles)
        if Role.ADMINISTRATOR.value not in role_list:
            role_list.append(Role.ADMINISTRATOR.value)
        transitions.append(
            LifecycleTransition(
                action=rule.action.value,
                label='',  # подпись из workflow_ui._ACTION_LABELS
                from_status=str(
                    rule.from_status.value
                    if isinstance(rule.from_status, VersionStatus)
                    else rule.from_status
                ),
                to_status=str(rule.to_status.value),
                roles=tuple(role_list),
                requires_comment=rule.requires_comment,
            )
        )

    return LifecycleProfile(
        statuses=statuses,
        transitions=tuple(transitions),
        create_roles=_role_set('curriculum_developer', 'administrator'),
        update_roles=_role_set('curriculum_developer', 'administrator'),
        view_roles=_role_set(
            'reader',
            'curriculum_developer',
            'reviewer',
            'manager',
            'administrator',
        ),
    )


def build_printed_form_lifecycle_profile() -> LifecycleProfile:
    return LifecycleProfile(
        statuses=(
            LifecycleStatus('new', 'Черновик'),
            LifecycleStatus('approved', 'Утверждён'),
            LifecycleStatus('trashed', 'В корзине'),
        ),
        transitions=(
            LifecycleTransition(
                action='approve',
                label='Утвердить',
                from_status='new',
                to_status='approved',
                roles=('reviewer', 'administrator'),
            ),
        ),
        create_roles=_role_set('reviewer', 'administrator'),
        update_roles=_role_set('reviewer', 'administrator'),
        view_roles=_role_set(
            'reader',
            'curriculum_developer',
            'reviewer',
            'manager',
            'administrator',
        ),
    )


def _parse_lifecycle(raw: dict | None) -> LifecycleProfile | None:
    if not raw:
        return None
    statuses = tuple(
        LifecycleStatus(code=str(item['code']), label=str(item['label']))
        for item in (raw.get('statuses') or [])
    )
    transitions = tuple(
        LifecycleTransition(
            action=str(item['action']),
            label=str(item.get('label') or ''),
            from_status=str(item['from']),
            to_status=str(item['to']),
            roles=tuple(str(r) for r in (item.get('roles') or ())),
            requires_comment=bool(item.get('requires_comment', False)),
        )
        for item in (raw.get('transitions') or [])
    )
    return LifecycleProfile(
        statuses=statuses,
        transitions=transitions,
        create_roles=frozenset(str(r) for r in (raw.get('create_roles') or ())),
        update_roles=frozenset(str(r) for r in (raw.get('update_roles') or ())),
        view_roles=frozenset(str(r) for r in (raw.get('view_roles') or ())),
    )


class SettingsLifecycleProvider:
    """Поставщик профилей из реестра видов (settings.DOCUMENT_TYPES)."""

    def profile_for(self, document_type: str) -> LifecycleProfile:
        from documents.document_types import get_spec, UnknownDocumentType

        key = str(document_type)
        try:
            spec = get_spec(key)
        except UnknownDocumentType:
            return build_plx_lifecycle_profile()
        if spec.lifecycle is not None:
            return spec.lifecycle
        return build_plx_lifecycle_profile()


_provider: SettingsLifecycleProvider | None = None


def get_lifecycle_provider() -> SettingsLifecycleProvider:
    global _provider
    if _provider is None:
        _provider = SettingsLifecycleProvider()
    return _provider


def reset_lifecycle_provider() -> None:
    """Сброс для тестов с override_settings."""
    global _provider
    _provider = None
    get_lifecycle_profile.cache_clear()


@lru_cache(maxsize=64)
def get_lifecycle_profile(document_type: str) -> LifecycleProfile:
    return get_lifecycle_provider().profile_for(document_type)


def _as_status_str(status: VersionStatus | str) -> str:
    return status.value if isinstance(status, VersionStatus) else str(status)


def _as_status(status: str) -> VersionStatus | str:
    try:
        return VersionStatus(status)
    except ValueError:
        return status


def _as_action(action: str) -> WorkflowAction | str:
    try:
        return WorkflowAction(action)
    except ValueError:
        return action


def _system_rules() -> tuple[TransitionRule, ...]:
    return tuple(
        rule
        for rule in TRANSITION_RULES
        if rule.action in (WorkflowAction.MOVE_TO_TRASH, WorkflowAction.RESTORE)
    )


def _business_rule_from_profile(
    profile: LifecycleProfile,
    from_status: str,
    to_status: str,
) -> TransitionRule | None:
    for item in profile.transitions:
        if item.from_status == from_status and item.to_status == to_status:
            to_enum = _as_status(item.to_status)
            if not isinstance(to_enum, VersionStatus):
                # Пока сервис переходов ожидает VersionStatus; неизвестный код — пропуск.
                continue
            from_enum: VersionStatus | str
            try:
                from_enum = VersionStatus(item.from_status)
            except ValueError:
                from_enum = item.from_status
            action = _as_action(item.action)
            if not isinstance(action, WorkflowAction):
                continue
            return TransitionRule(
                from_status=from_enum,
                to_status=to_enum,
                action=action,
                requires_comment=item.requires_comment,
                allowed_roles=frozenset(item.roles) if item.roles else None,
                action_label_override=item.label or None,
            )
    return None


def get_rule_for_type(
    from_status: VersionStatus | str,
    to_status: VersionStatus | str,
    *,
    document_type: str | None = None,
) -> TransitionRule | None:
    """Правило перехода с учётом профиля вида (плюс системные trash/restore)."""
    src = _as_status_str(from_status)
    dst = _as_status_str(to_status)
    doc_type = document_type or 'plx'

    for rule in _system_rules():
        if _as_status_str(rule.to_status) != dst:
            continue
        if rule.from_status == ANY_STATUS and src not in {
            _as_status_str(s) for s in rule.exclude_from
        }:
            return rule
        if _as_status_str(rule.from_status) == src:
            return rule

    profile = get_lifecycle_profile(doc_type)
    return _business_rule_from_profile(profile, src, dst)


def list_rules_for_type(
    from_status: VersionStatus | str,
    *,
    document_type: str | None = None,
) -> list[TransitionRule]:
    src = _as_status_str(from_status)
    doc_type = document_type or 'plx'
    profile = get_lifecycle_profile(doc_type)

    rules: list[TransitionRule] = []
    seen: set[str] = set()

    for item in profile.transitions:
        if item.from_status != src:
            continue
        rule = _business_rule_from_profile(profile, item.from_status, item.to_status)
        if rule is None:
            continue
        key = _as_status_str(rule.to_status)
        if key not in seen:
            rules.append(rule)
            seen.add(key)

    for rule in _system_rules():
        matches = _as_status_str(rule.from_status) == src or (
            rule.from_status == ANY_STATUS
            and src not in {_as_status_str(s) for s in rule.exclude_from}
        )
        key = _as_status_str(rule.to_status)
        if matches and key not in seen:
            rules.append(rule)
            seen.add(key)

    return rules


def status_label_for_type(status: VersionStatus | str, document_type: str | None) -> str:
    code = _as_status_str(status)
    if document_type:
        label = get_lifecycle_profile(document_type).status_label(code)
        if label:
            return label
    # Запасной путь: choices модели / код.
    from documents.models import VersionStatus as OrmVersionStatus

    return dict(OrmVersionStatus.choices).get(code, code)


def action_label_for_type(action: WorkflowAction | str, document_type: str | None) -> str | None:
    key = action.value if isinstance(action, WorkflowAction) else str(action)
    if document_type:
        label = get_lifecycle_profile(document_type).action_label(key)
        if label:
            return label
    return None


def user_has_lifecycle_role(user_roles: frozenset, allowed: frozenset[str]) -> bool:
    from accounts.roles import Role

    if Role.ADMINISTRATOR in user_roles:
        return True
    return bool({r.value for r in user_roles} & set(allowed))
