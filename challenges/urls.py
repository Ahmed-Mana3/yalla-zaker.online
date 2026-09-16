from django.urls import path

from . import views

urlpatterns = [
    path('', views.challenge_index, name='challenges'),
    path('create/', views.challenge_create, name='challenge_create'),
    path('<int:pk>/', views.challenge_detail, name='challenge_detail'),
    path('<int:pk>/join/', views.challenge_join, name='challenge_join'),
]