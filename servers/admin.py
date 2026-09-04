from django.contrib import admin

from .models import Server, ServerLongTermRequest, ServerUsageSnapshot


@admin.register(Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "location")
    list_filter = ("category",)
    search_fields = ("name",)


@admin.register(ServerUsageSnapshot)
class ServerUsageSnapshotAdmin(admin.ModelAdmin):
    list_display = ("server", "captured_at", "cpu_percent", "memory_percent", "disk_percent", "gpu_percent")
    list_filter = ("server",)
    date_hierarchy = "captured_at"


@admin.register(ServerLongTermRequest)
class ServerLongTermRequestAdmin(admin.ModelAdmin):
    list_display = ("server", "user", "start_date", "end_date", "status", "reviewed_by", "reviewed_at")
    list_filter = ("status", "server")
