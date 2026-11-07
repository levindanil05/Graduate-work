"""
Django settings for education_site.

Значения, влияющие на безопасность и окружение, берутся из переменных окружения.
См. .env.example и docs/deployment.md.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


def _env_list(name: str, default: list[str] | None = None) -> list[str]:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return list(default or [])
    return [item.strip() for item in raw.split(',') if item.strip()]


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
DEBUG = _env_bool('DJANGO_DEBUG', default=True)

if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'django-insecure-dev-only-change-me'
    else:
        raise RuntimeError('DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is false')

ALLOWED_HOSTS = _env_list('DJANGO_ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])
CSRF_TRUSTED_ORIGINS = _env_list('DJANGO_CSRF_TRUSTED_ORIGINS')

# За reverse-proxy (nginx завершает TLS)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = _env_bool('DJANGO_USE_X_FORWARDED_HOST', default=True)

# Подпуть (если сервис висит на /plans-app/ и т.п.)
FORCE_SCRIPT_NAME = os.getenv('DJANGO_FORCE_SCRIPT_NAME') or None

FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv('FILE_UPLOAD_MAX_MEMORY_SIZE', str(10 * 1024 * 1024)))
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.getenv('DATA_UPLOAD_MAX_MEMORY_SIZE', str(55 * 1024 * 1024)))
PLX_UPLOAD_MAX_BYTES = int(os.getenv('PLX_UPLOAD_MAX_BYTES', str(50 * 1024 * 1024)))
PLX_PARSE_TIMEOUT_SECONDS = int(os.getenv('PLX_PARSE_TIMEOUT_SECONDS', '10'))

MEDIA_URL = os.getenv('MEDIA_URL', '/files/')
MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', str(BASE_DIR / 'files')))
USERFILES_ROOT = Path(os.getenv('USERFILES_ROOT', str(BASE_DIR / 'userfiles')))

# ---------------------------------------------------------------------------
# Security (prod)
# ---------------------------------------------------------------------------

SECURE_SSL_REDIRECT = _env_bool('DJANGO_SECURE_SSL_REDIRECT', default=not DEBUG)
SESSION_COOKIE_SECURE = _env_bool('DJANGO_SESSION_COOKIE_SECURE', default=not DEBUG)
CSRF_COOKIE_SECURE = _env_bool('DJANGO_CSRF_COOKIE_SECURE', default=not DEBUG)
SECURE_HSTS_SECONDS = int(os.getenv('DJANGO_SECURE_HSTS_SECONDS', '0' if DEBUG else '31536000'))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', default=not DEBUG)
SECURE_HSTS_PRELOAD = _env_bool('DJANGO_SECURE_HSTS_PRELOAD', default=False)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_AGE = int(os.getenv('DJANGO_SESSION_COOKIE_AGE', str(60 * 60 * 8)))
SESSION_SAVE_EVERY_REQUEST = True

ADMIN_URL_PATH = os.getenv('DJANGO_ADMIN_URL_PATH', 'admin/').strip('/') + '/'

# ---------------------------------------------------------------------------
# Branding (UI)
# ---------------------------------------------------------------------------

BRANDING = {
    'product_name': os.getenv(
        'BRANDING_PRODUCT_NAME',
        'Сервис для согласования изменений в учебных планах',
    ),
    'product_short_name': os.getenv('BRANDING_PRODUCT_SHORT_NAME', 'Согласование УП'),
    'organization_name': os.getenv(
        'BRANDING_ORGANIZATION_NAME',
        'Волгоградский государственный технический университет',
    ),
    'organization_short_name': os.getenv('BRANDING_ORGANIZATION_SHORT_NAME', 'ВолгГТУ'),
    'unit_name': os.getenv('BRANDING_UNIT_NAME', 'Учебный отдел'),
    'logo': os.getenv('BRANDING_LOGO', 'ui/img/logo-vstu.svg'),
    'logo_small': os.getenv('BRANDING_LOGO_SMALL', 'ui/img/logo-vstu-mark.svg'),
    'favicon': os.getenv('BRANDING_FAVICON', 'ui/img/favicon.svg'),
    'support_email': os.getenv('BRANDING_SUPPORT_EMAIL', ''),
    'footer_text': os.getenv(
        'BRANDING_FOOTER_TEXT',
        'ВолгГТУ · Сервис согласования учебных планов',
    ),
    'primary_color': os.getenv('BRANDING_PRIMARY_COLOR', '#003366'),
    'accent_color': os.getenv('BRANDING_ACCENT_COLOR', '#c8102e'),
    'app_version': os.getenv('APP_VERSION', 'dev'),
}

# ---------------------------------------------------------------------------
# Apps / middleware
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_tables2',
    'django_filters',
    'documents',
    'external_sync',
    'accounts',
    'plans',
    'feedback',
    'helpcenter',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'accounts.middleware.LoginRateLimitMiddleware',
]

ROOT_URLCONF = 'education_site.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'accounts.context_processors.role_context',
                'accounts.context_processors.branding_context',
                'accounts.context_processors.nav_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'education_site.wsgi.application'

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DATABASE_URL = os.getenv('DATABASE_URL', '')
if DATABASE_URL:
    parsed = urlparse(DATABASE_URL)
    engine = 'django.db.backends.postgresql'
    if parsed.scheme in {'postgres', 'postgresql'}:
        engine = 'django.db.backends.postgresql'
    elif parsed.scheme == 'sqlite':
        engine = 'django.db.backends.sqlite3'
    DATABASES = {
        'default': {
            'ENGINE': engine,
            'NAME': parsed.path.lstrip('/') if engine.endswith('postgresql') else (parsed.path or BASE_DIR / 'db.sqlite3'),
            'USER': parsed.username or '',
            'PASSWORD': parsed.password or '',
            'HOST': parsed.hostname or '',
            'PORT': str(parsed.port or ''),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {'min_length': 10},
    },
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/accounts/login/'

LOGIN_RATE_LIMIT_ATTEMPTS = int(os.getenv('LOGIN_RATE_LIMIT_ATTEMPTS', '5'))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv('LOGIN_RATE_LIMIT_WINDOW_SECONDS', '900'))

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static
# ---------------------------------------------------------------------------

STATIC_URL = os.getenv('STATIC_URL', '/static/')
STATIC_ROOT = Path(os.getenv('STATIC_ROOT', str(BASE_DIR / 'staticfiles')))
STATICFILES_DIRS = [BASE_DIR / 'static']
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'
        if not DEBUG
        else 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
    },
    'loggers': {
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# ---------------------------------------------------------------------------
# External storage (tokens only via env)
# ---------------------------------------------------------------------------

YANDEX_DISK_TOKEN = os.getenv('YANDEX_DISK_TOKEN')
YANDEX_DISK_BASE_PATH = os.getenv('YANDEX_DISK_BASE_PATH') or '/'
YANDEX_DISK_UO_READONLY_TOKEN = os.getenv('YANDEX_DISK_UO_READONLY_TOKEN')
YANDEX_DISK_UO_READONLY_BASE_PATH = os.getenv('YANDEX_DISK_UO_READONLY_BASE_PATH') or '/'
YANDEX_DISK_MIKE_RW_TOKEN = os.getenv('YANDEX_DISK_MIKE_RW_TOKEN')
YANDEX_DISK_MIKE_RW_BASE_PATH = os.getenv('YANDEX_DISK_MIKE_RW_BASE_PATH') or '/'

# ---------------------------------------------------------------------------
# Trash retention
# ---------------------------------------------------------------------------

TRASH_RETENTION_DAYS = int(os.getenv('TRASH_RETENTION_DAYS', '30'))
DEFAULT_PAGE_SIZE = int(os.getenv('DEFAULT_PAGE_SIZE', '50'))
SYNC_SCHEDULE_INTERVAL_SECONDS = int(os.getenv('SYNC_SCHEDULE_INTERVAL_SECONDS', '3600'))
SYNC_WORKER_POLL_SECONDS = int(os.getenv('SYNC_WORKER_POLL_SECONDS', '30'))
