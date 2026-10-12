from django.urls import path

from . import views

urlpatterns = [
    path('', views.room_index, name='rooms'),
    path('new/', views.room_create, name='room_create'),
    path('join/', views.room_join_code, name='room_join_code'),
    path('invite/<str:token>/', views.room_invite, name='room_invite'),
    path('invite/<str:token>/join/', views.room_join, name='room_join'),
    path('<int:pk>/', views.room_detail, name='room_detail'),
    path('<int:pk>/state/', views.room_state_api, name='room_state_api'),
    path('<int:pk>/edit/', views.room_edit, name='room_edit'),
    path('<int:pk>/delete/', views.room_delete, name='room_delete'),
    path('<int:pk>/leave/', views.room_leave, name='room_leave'),
    path('<int:pk>/goal/', views.room_goal, name='room_goal'),
    path('<int:pk>/new-link/', views.room_regenerate_invite, name='room_regenerate_invite'),
    path('<int:pk>/lock/', views.room_toggle_lock, name='room_toggle_lock'),
    path('<int:pk>/kick/<int:user_id>/', views.room_kick, name='room_kick'),
    path('<int:pk>/unban/<int:user_id>/', views.room_unban, name='room_unban'),
]
