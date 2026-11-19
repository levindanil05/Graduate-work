from django.urls import path

from . import views

app_name = 'helpcenter'

urlpatterns = [
    path('', views.help_index, name='index'),
    path('how-it-works/', views.how_it_works, name='how_it_works'),
    path('about/', views.about, name='about'),
    path('glossary/', views.glossary_index, name='glossary'),
    path('glossary/<slug:slug>/', views.glossary_term, name='glossary_term'),
]
