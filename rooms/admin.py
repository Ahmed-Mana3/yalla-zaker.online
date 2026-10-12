from django.contrib import admin

from .models import Room, RoomBan, RoomMember


class RoomMemberInline(admin.TabularInline):
    model = RoomMember
    extra = 0


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'visibility', 'capacity', 'is_locked', 'created_at')
    list_filter = ('visibility', 'is_locked')
    search_fields = ('name', 'owner__username')
    inlines = [RoomMemberInline]


admin.site.register(RoomBan)
