from __future__ import annotations

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render

from documents.entities import VersionStatus
from documents.workflow_rules import ANY_STATUS, TRANSITION_RULES
from documents.workflow_ui import action_label, target_status_label

from .glossary import all_terms, get_term

# Основная цепочка согласования (для наглядной схемы)
MAIN_FLOW_STATUSES: tuple[VersionStatus, ...] = (
    VersionStatus.NEW,
    VersionStatus.ON_REVIEW,
    VersionStatus.NEEDS_FIX,
    VersionStatus.APPROVED,
    VersionStatus.ARCHIVED,
)


def process_diagram_context(*, current_status: str | VersionStatus | None = None) -> dict:
    """Данные схемы процесса; current_status подсвечивает «Вы здесь»."""
    current = None
    if current_status is not None:
        current = (
            current_status
            if isinstance(current_status, VersionStatus)
            else VersionStatus(str(current_status))
        )
    stages = []
    for status in MAIN_FLOW_STATUSES:
        stages.append(
            {
                'status': status.value,
                'label': target_status_label(status),
                'is_current': current == status,
            }
        )
    side_stages = []
    for status in (VersionStatus.INVALID, VersionStatus.TRASHED):
        side_stages.append(
            {
                'status': status.value,
                'label': target_status_label(status),
                'is_current': current == status,
            }
        )
    next_hint = ''
    if current == VersionStatus.NEW:
        next_hint = 'Следующий шаг: отправить план на проверку в учебный отдел.'
    elif current == VersionStatus.ON_REVIEW:
        next_hint = 'Сейчас план проверяет учебный отдел: утвердит или отправит на доработку.'
    elif current == VersionStatus.NEEDS_FIX:
        next_hint = 'Нужна доработка на кафедре, затем повторная отправка на проверку.'
    elif current == VersionStatus.APPROVED:
        next_hint = 'План утверждён. При замене новой утверждённой версией эта уйдёт в архив.'
    elif current == VersionStatus.ARCHIVED:
        next_hint = 'Версия в архиве — сохранена в истории.'
    elif current == VersionStatus.INVALID:
        next_hint = 'Файл не удалось прочитать. Загрузите исправленный файл или отправьте в корзину.'
    elif current == VersionStatus.TRASHED:
        next_hint = 'Документ в корзине. Его можно восстановить или окончательно удалить (администратор).'

    transitions = []
    for rule in TRANSITION_RULES:
        from_label = (
            'Любой (кроме корзины)'
            if rule.from_status == ANY_STATUS
            else target_status_label(rule.from_status)
        )
        transitions.append(
            {
                'from': from_label,
                'to': target_status_label(rule.to_status),
                'action': action_label(rule.action),
                'requires_comment': rule.requires_comment,
            }
        )
    return {
        'stages': stages,
        'side_stages': side_stages,
        'next_hint': next_hint,
        'current_status': current.value if current else '',
        'transitions': transitions,
    }


def help_index(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        'helpcenter/index.html',
        {
            'terms': all_terms()[:12],
        },
    )


def how_it_works(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        'helpcenter/how_it_works.html',
        {'process_diagram': process_diagram_context()},
    )


def about(request: HttpRequest) -> HttpResponse:
    return render(request, 'helpcenter/about.html')


def glossary_index(request: HttpRequest) -> HttpResponse:
    return render(request, 'helpcenter/glossary_index.html', {'terms': all_terms()})


def glossary_term(request: HttpRequest, slug: str) -> HttpResponse:
    term = get_term(slug)
    if term is None:
        raise Http404
    return render(request, 'helpcenter/glossary_term.html', {'term': term})
