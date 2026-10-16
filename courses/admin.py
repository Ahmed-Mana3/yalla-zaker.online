from django.contrib import admin

from .models import Course, Roadmap, RoadmapCourse


class RoadmapCourseInline(admin.TabularInline):
    model = RoadmapCourse
    extra = 0


@admin.register(Roadmap)
class RoadmapAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'step_count', 'is_public', 'created_at')
    list_filter = ('is_public',)
    search_fields = ('title',)
    inlines = [RoadmapCourseInline]


@admin.register(RoadmapCourse)
class RoadmapCourseAdmin(admin.ModelAdmin):
    list_display = ('roadmap', 'course', 'position', 'planned_hours', 'link')
    list_filter = ('roadmap',)
    ordering = ('roadmap', 'position')


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'kind', 'total_hours', 'hours_done', 'total_pages', 'pages_done', 'is_public', 'created_at')
    list_filter = ('kind', 'is_public')
    search_fields = ('title',)