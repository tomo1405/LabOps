from django.contrib import admin

from .models import AttendanceLog, AttendanceStatus, CanteenMenu, NewsPost, NfcTag


@admin.register(AttendanceStatus)
class AttendanceStatusAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "updated_at")
    list_filter = ("status",)


@admin.register(NfcTag)
class NfcTagAdmin(admin.ModelAdmin):
    list_display = ("label", "location", "is_active", "url_path", "created_at")
    list_filter = ("is_active",)
    readonly_fields = ("token", "url_path", "created_at")

    @admin.display(description="タグに書き込むURL")
    def url_path(self, obj) -> str:
        return obj.url_path


@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
    list_display = ("recorded_at", "user", "action", "source", "tag")
    list_filter = ("action", "source", "user")
    date_hierarchy = "recorded_at"
    readonly_fields = ("recorded_at",)


@admin.register(CanteenMenu)
class CanteenMenuAdmin(admin.ModelAdmin):
    list_display = ("date", "source")
    list_filter = ("source",)
    date_hierarchy = "date"


@admin.register(NewsPost)
class NewsPostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "status", "published_at")
    list_filter = ("status", "author")
    search_fields = ("title", "body")
