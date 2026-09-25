from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from accounts.permissions import primary_role_display


@require_http_methods(['GET', 'POST'])
def login_view(request: HttpRequest) -> HttpResponse:
    if request.user.is_authenticated:
        return redirect('plans:plan_list')

    error = ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get('next') or request.POST.get('next') or ''
            if next_url.startswith('/'):
                return redirect(next_url)
            return redirect('plans:plan_list')
        error = 'Неверный логин или пароль'

    return render(
        request,
        'accounts/login.html',
        {
            'error': error,
            'next': request.GET.get('next', ''),
        },
    )


@login_required
def logout_view(request: HttpRequest) -> HttpResponse:
    logout(request)
    return redirect('accounts:login')


def role_context(request: HttpRequest) -> dict:
    if not request.user.is_authenticated:
        return {'user_role_label': ''}
    return {'user_role_label': primary_role_display(request.user.pk)}
