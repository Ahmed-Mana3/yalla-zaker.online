from django.urls import path

from . import views

urlpatterns = [
    path('', views.course_index, name='courses'),
    path('add/', views.course_create, name='course_create'),

    path('roadmaps/', views.roadmap_index, name='roadmaps'),
    path('roadmaps/add/', views.roadmap_create, name='roadmap_create'),
    path('roadmaps/<slug:slug>/', views.roadmap_detail, name='roadmap_detail'),
    path('roadmaps/<slug:slug>/edit/', views.roadmap_edit, name='roadmap_edit'),
    path('roadmaps/<slug:slug>/delete/', views.roadmap_delete, name='roadmap_delete'),
    path('roadmaps/<slug:slug>/add-courses/', views.roadmap_add_course, name='roadmap_add_course'),
    path('roadmaps/<slug:slug>/steps/', views.roadmap_steps_edit, name='roadmap_steps_edit'),
    path('roadmaps/<slug:slug>/add-step/', views.roadmap_add_step, name='roadmap_add_step'),
    path('roadmaps/<slug:slug>/reorder/', views.roadmap_reorder, name='roadmap_reorder'),
    path('roadmaps/<slug:slug>/step/<int:step_id>/remove/', views.roadmap_remove_step, name='roadmap_remove_step'),
    path('roadmaps/<slug:slug>/step/<int:step_id>/label/', views.roadmap_edit_step, name='roadmap_edit_step'),
    path('roadmaps/<slug:slug>/clone/', views.roadmap_clone, name='roadmap_clone'),

    path('<slug:slug>/', views.course_detail, name='course_detail'),
    path('<slug:slug>/edit/', views.course_edit, name='course_edit'),
    path('<slug:slug>/delete/', views.course_delete, name='course_delete'),
]