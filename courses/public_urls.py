"""Public, share-by-link course URLs — no auth required."""
from django.urls import path

from . import views

app_name = 'public'

urlpatterns = [
    path('<slug:slug>/', views.course_public, name='course_public'),
    path('r/<slug:slug>/', views.roadmap_public, name='roadmap_public'),
]