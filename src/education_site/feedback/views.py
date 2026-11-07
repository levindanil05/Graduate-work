from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from accounts.permissions import primary_role_display, user_can_manage_feedback
from documents.models import Document

from .forms import FeedbackCreateFormSimple, FeedbackHandleFormSimple
from .models import FeedbackReport


def _build_context(request: HttpRequest) -> dict:
    ctx: dict = {
        'page_url': request.build_absolute_uri(),
        'route_name': '',
        'document_id': '',
        'version_id': '',
        'document_status': '',
        'version_status': '',
        'last_workflow_action': '',
        'user_role': primary_role_display(request.user.pk) if request.user.is_authenticated else '',
        'app_version': settings.BRANDING.get('app_version', ''),
        'user_agent': request.META.get('HTTP_USER_AGENT', '')[:500],
    }
    match = request.resolver_match
    if match:
        ctx['route_name'] = match.view_name or ''
        for key in ('document_id', 'version_id'):
            if key in match.kwargs:
                ctx[key] = str(match.kwargs[key])
    document_id = request.GET.get('document_id') or request.POST.get('document_id')
    if document_id:
        ctx['document_id'] = document_id
        doc = Document.objects.filter(pk=document_id).select_related('current_version').first()
        if doc and doc.current_version_id:
            ctx['version_id'] = str(doc.current_version_id)
            status_label = doc.current_version.get_status_display()
            ctx['version_status'] = status_label
            ctx['document_status'] = status_label
    return ctx


@login_required
@require_http_methods(['GET', 'POST'])
def feedback_create(request: HttpRequest) -> HttpResponse:
    initial_document = None
    document_id = request.GET.get('document_id') or request.POST.get('document_id')
    if document_id:
        initial_document = Document.objects.filter(pk=document_id).first()

    if request.method == 'POST':
        form = FeedbackCreateFormSimple(request.POST)
        if form.is_valid():
            report = form.save(commit=False)
            report.author = request.user
            report.context = _build_context(request)
            if initial_document:
                report.document = initial_document
            report.save()
            messages.success(request, 'Обращение отправлено. Спасибо!')
            return redirect('feedback:my_list')
    else:
        form = FeedbackCreateFormSimple()

    return render(
        request,
        'feedback/create.html',
        {
            'form': form,
            'document': initial_document,
        },
    )


@login_required
def feedback_my_list(request: HttpRequest) -> HttpResponse:
    reports = FeedbackReport.objects.filter(author=request.user).order_by('-created_at')[:200]
    return render(request, 'feedback/my_list.html', {'reports': reports})


def _require_feedback_staff(request: HttpRequest) -> None:
    if not user_can_manage_feedback(request.user.pk):
        raise PermissionDenied('Обработка обращений доступна управляющему или администратору')


@login_required
def feedback_staff_list(request: HttpRequest) -> HttpResponse:
    _require_feedback_staff(request)
    status = request.GET.get('status', '')
    qs = FeedbackReport.objects.select_related('author', 'document', 'handled_by').order_by(
        '-created_at'
    )
    if status:
        qs = qs.filter(status=status)
    return render(
        request,
        'feedback/staff_list.html',
        {
            'reports': qs[:500],
            'status_filter': status,
        },
    )


@login_required
@require_http_methods(['GET', 'POST'])
def feedback_staff_detail(request: HttpRequest, report_id) -> HttpResponse:
    _require_feedback_staff(request)
    report = get_object_or_404(
        FeedbackReport.objects.select_related('author', 'document', 'handled_by'),
        pk=report_id,
    )

    if request.method == 'POST':
        form = FeedbackHandleFormSimple(request.POST, instance=report)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.handled_by = request.user
            updated.handled_at = timezone.now()
            updated.save()
            messages.success(request, 'Обращение обновлено.')
            return redirect('feedback:staff_detail', report_id=report.pk)
    else:
        form = FeedbackHandleFormSimple(instance=report)

    return render(
        request,
        'feedback/staff_detail.html',
        {
            'report': report,
            'form': form,
            'context_pretty': report.context or {},
        },
    )
