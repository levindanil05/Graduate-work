from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from education_site.health import healthz

urlpatterns = [
    path(settings.ADMIN_URL_PATH, admin.site.urls),
    path('healthz', healthz, name='healthz'),
    path('accounts/', include('accounts.urls')),
    path('feedback/', include('feedback.urls')),
    path('help/', include('helpcenter.urls')),
    path('', include('plans.urls')),
]

handler404 = 'education_site.views_errors.page_not_found'
handler500 = 'education_site.views_errors.server_error'

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
