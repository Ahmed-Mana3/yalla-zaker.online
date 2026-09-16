from django.contrib import admin

from .models import Friendship, Profile

admin.site.register(Profile)
admin.site.register(Friendship)