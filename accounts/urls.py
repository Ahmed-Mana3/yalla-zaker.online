from django.contrib.auth.views import LoginView
from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('signup/', views.signup, name='signup'),
    path(
        'login/',
        LoginView.as_view(
            template_name='accounts/auth.html',
            redirect_authenticated_user=True,
            extra_context={'mode': 'login'},
        ),
        name='login',
    ),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/', views.profile_edit, name='profile_edit'),
    path('users/<str:username>/', views.profile_view, name='profile'),

    # Friends
    path('friends/', views.friends_index, name='friends'),
    path('friends/add/<int:user_id>/', views.friend_request, name='friend_request'),
    path('friends/accept/<int:friendship_id>/', views.friend_accept, name='friend_accept'),
    path('friends/decline/<int:friendship_id>/', views.friend_decline, name='friend_decline'),
    path('friends/remove/<int:friend_id>/', views.friend_remove, name='friend_remove'),
]