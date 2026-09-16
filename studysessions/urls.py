from django.urls import path

from . import views

urlpatterns = [
    path('', views.study_index, name='study'),
    path('start/', views.session_start, name='session_start'),
    path('pause/', views.session_pause, name='session_pause'),
    path('resume/', views.session_resume, name='session_resume'),
    path('end/', views.session_end, name='session_end'),
    path('log/', views.session_log, name='session_log'),
    path('api/state/', views.session_state_api, name='session_state_api'),
]