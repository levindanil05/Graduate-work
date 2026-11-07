from django.urls import path

from . import document_views, home_views, upload_views, views
from . import export_views, views_registry

app_name = 'plans'

urlpatterns = [
    path('', home_views.home, name='home'),
    path('plans/', views_registry.plan_list, name='plan_list'),
    path('plans/trash/', views_registry.trash_list, name='trash_list'),
    path(
        'plans/trash/<uuid:document_id>/hard-delete/',
        views_registry.hard_delete_document,
        name='hard_delete_document',
    ),
    path('plans/bulk/', views_registry.bulk_registry_action, name='bulk_registry'),
    path('plans/export.csv', export_views.export_csv, name='export_csv'),
    path('plans/export.xlsx', export_views.export_xlsx, name='export_xlsx'),
    path('add/', views.plan_add, name='plan_add'),
    path('upload/', upload_views.upload_plx, name='upload_plx'),
    path('sync-yandex/', views.sync_yandex, name='sync_yandex'),
    path('sync/', views.external_sync_dashboard, name='external_sync_dashboard'),
    path('sync/diagnostics/', views.connection_diagnostics, name='connection_diagnostics'),
    path('sync/runs/<uuid:run_id>/', views.sync_run_detail, name='sync_run_detail'),
    path('doc/<uuid:document_id>/', document_views.document_detail, name='document_detail'),
    path('doc/<uuid:document_id>/transition/', document_views.transition_status, name='transition_status'),
    path('doc/<uuid:document_id>/download/', document_views.download_current, name='download_current'),
    path(
        'doc/<uuid:document_id>/versions/<uuid:version_id>/download/',
        document_views.download_version,
        name='download_version',
    ),
]
