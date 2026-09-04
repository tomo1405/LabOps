from django.contrib import admin

from .models import AttendanceStatus, CanteenMenu, NewsPost


@admin.register(AttendanceStatus)
class AttendanceStatusAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "updated_at")
    list_filter = ("status",)


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
