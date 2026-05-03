from django.urls import path
from . import views

app_name = 'plans'

urlpatterns = [
    path('', views.plan_list, name='plan_list'),
    path('add/', views.plan_add, name='plan_add'),
    path('sync-yandex/', views.sync_yandex, name='sync_yandex'),
]