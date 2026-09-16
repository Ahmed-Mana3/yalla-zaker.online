from django.contrib import admin

from .models import BreakSegment, StudySegment, StudySession

admin.site.register(StudySession)
admin.site.register(StudySegment)
admin.site.register(BreakSegment)