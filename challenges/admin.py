from django.contrib import admin

from .models import Challenge, ChallengeMember

admin.site.register(Challenge)
admin.site.register(ChallengeMember)