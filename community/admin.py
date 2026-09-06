from django.contrib import admin

from .models import (
    AttendanceLog,
    AttendanceStatus,
    CanteenMenu,
    CanteenMenuItem,
    NewsPost,
    NfcTag,
)


@admin.register(AttendanceStatus)
class AttendanceStatusAdmin(admin.ModelAdmin):
    list_display = ("user", "status", "updated_at")
    list_filter = ("status",)


@admin.register(NfcTag)
class NfcTagAdmin(admin.ModelAdmin):
    """NFCタグの発行。URLがそのまま打刻の鍵になるため、発行は管理者のみが行う。"""

    list_display = ("user", "label", "location", "is_active", "url_path", "created_at")
    list_filter = ("is_active", "user")
    search_fields = ("user__name", "user__email", "label", "location")
    autocomplete_fields = ()
    readonly_fields = ("token", "url_path", "created_at")
    actions = ("regenerate_tokens", "deactivate_tags")
    fieldsets = (
        (None, {"fields": ("user", "label", "location", "is_active")}),
        (
            "タグに書き込むURL",
            {
                "fields": ("url_path", "token", "created_at"),
                "description": (
                    "このURLを開くと、対象メンバーの在室／不在がログインなしで反転します。"
                    "URLを知っていれば誰でも打刻できるため、配布先に注意してください。"
                    "紛失した場合は「トークンを再発行する」で古いURLを無効にできます。"
                ),
            },
        ),
    )

    @admin.display(description="タグに書き込むURL")
    def url_path(self, obj) -> str:
        return obj.url_path

    @admin.action(description="トークンを再発行する（古いURLは使えなくなります）")
    def regenerate_tokens(self, request, queryset):
        for tag in queryset:
            tag.regenerate_token()
        self.message_user(request, f"{queryset.count()} 件のトークンを再発行しました。")

    @admin.action(description="無効にする")
    def deactivate_tags(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} 件を無効にしました。")


@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
    list_display = ("recorded_at", "user", "action", "source", "tag")
    list_filter = ("action", "source", "user")
    date_hierarchy = "recorded_at"
    readonly_fields = ("recorded_at",)


class CanteenMenuItemInline(admin.TabularInline):
    model = CanteenMenuItem
    extra = 1


@admin.register(CanteenMenu)
class CanteenMenuAdmin(admin.ModelAdmin):
    inlines = [CanteenMenuItemInline]
    list_display = ("date", "source")
    list_filter = ("source",)
    date_hierarchy = "date"


@admin.register(NewsPost)
class NewsPostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "status", "published_at")
    list_filter = ("status", "author")
    search_fields = ("title", "body")
