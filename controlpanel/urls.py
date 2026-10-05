"""URL map for the exclusive control panel.

Mounted at ``/exclusive-admin/`` with an ``app_name`` so every pattern stays
namespaced as ``controlpanel:…`` and cannot collide with the site's own URLs.
"""

from django.urls import path

from . import views

app_name = 'controlpanel'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('unlock/', views.unlock, name='unlock'),
    path('lock/', views.lock, name='lock'),
    path('bulk-delete/<str:model_key>/', views.bulk_delete, name='bulk_delete'),
    path('toggle/<str:model_key>/<int:pk>/<str:field_name>/', views.toggle_flag, name='toggle_flag'),
    path('duplicate/<str:model_key>/<int:pk>/', views.duplicate, name='duplicate'),
    path('<str:model_key>/', views.records, name='records'),
    path('<str:model_key>/add/', views.record_add, name='record_add'),
    path('<str:model_key>/<int:pk>/', views.record_delete, name='record_delete'),
    path('<str:model_key>/<int:pk>/edit/', views.record_edit, name='record_edit'),
]