from django.contrib import admin

from .models import (
    ConferenceChecklistItem,
    ConferencePrep,
    DiaryAttachment,
    DiaryComment,
    DiaryEntry,
    ScheduleEvent,
)


class DiaryAttachmentInline(admin.TabularInline):
    model = DiaryAttachment
    extra = 0
    readonly_fields = ("original_name", "uploaded_at")


class DiaryCommentInline(admin.TabularInline):
    model = DiaryComment
    extra = 0
    readonly_fields = ("created_at",)


@admin.register(DiaryEntry)
class DiaryEntryAdmin(admin.ModelAdmin):
    list_display = ("date", "user", "visibility", "tags", "like_total", "updated_at")

    @admin.display(description="いいね")
    def like_total(self, obj) -> int:
        return obj.likes.count()

    list_filter = ("user", "visibility", "date")
    inlines = [DiaryAttachmentInline, DiaryCommentInline]
    search_fields = ("content", "tags")
    date_hierarchy = "date"


class ConferenceChecklistItemInline(admin.TabularInline):
    model = ConferenceChecklistItem
    extra = 1


@admin.register(ConferencePrep)
class ConferencePrepAdmin(admin.ModelAdmin):
    list_display = ("conference_name", "deadline", "user")
    list_filter = ("user",)
    search_fields = ("conference_name",)
    inlines = [ConferenceChecklistItemInline]


@admin.register(ScheduleEvent)
class ScheduleEventAdmin(admin.ModelAdmin):
    list_display = ("title", "start_at", "end_at", "event_type", "user", "conference")
    list_filter = ("event_type", "user")
    search_fields = ("title",)
    date_hierarchy = "start_at"
