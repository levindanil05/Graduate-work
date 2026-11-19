from django.urls import path

from . import views

app_name = 'feedback'

urlpatterns = [
    path('new/', views.feedback_create, name='create'),
    path('mine/', views.feedback_my_list, name='my_list'),
    path('mine/<uuid:report_id>/', views.feedback_my_detail, name='my_detail'),
    path('staff/', views.feedback_staff_list, name='staff_list'),
    path('staff/<uuid:report_id>/', views.feedback_staff_detail, name='staff_detail'),
]
