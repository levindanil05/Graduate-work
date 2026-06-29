from django.urls import path

from . import document_views, upload_views, views

app_name = 'plans'

urlpatterns = [
    path('', views.plan_list, name='plan_list'),
    path('add/', views.plan_add, name='plan_add'),
    path('upload/', upload_views.upload_plx, name='upload_plx'),
    path('sync-yandex/', views.sync_yandex, name='sync_yandex'),
    path('doc/<uuid:document_id>/', document_views.document_detail, name='document_detail'),
    path('doc/<uuid:document_id>/transition/', document_views.transition_status, name='transition_status'),
    path('doc/<uuid:document_id>/download/', document_views.download_current, name='download_current'),
    path(
        'doc/<uuid:document_id>/versions/<uuid:version_id>/download/',
        document_views.download_version,
        name='download_version',
    ),
]
