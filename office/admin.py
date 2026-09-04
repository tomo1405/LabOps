from django.contrib import admin

from .models import (
    JobHuntingStory,
    ObVisitRequest,
    Ticket,
    TicketComment,
    TravelExpenseRequest,
)


@admin.register(TravelExpenseRequest)
class TravelExpenseRequestAdmin(admin.ModelAdmin):
    list_display = ("destination", "user", "amount", "travel_start", "travel_end", "status", "approved_by")
    list_filter = ("status",)


class TicketCommentInline(admin.TabularInline):
    model = TicketComment
    extra = 1


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("title", "requester", "status", "priority", "updated_at")
    list_filter = ("status", "priority")
    search_fields = ("title", "description")
    inlines = [TicketCommentInline]


@admin.register(JobHuntingStory)
class JobHuntingStoryAdmin(admin.ModelAdmin):
    list_display = ("user", "is_public", "created_at")
    list_filter = ("is_public",)


@admin.register(ObVisitRequest)
class ObVisitRequestAdmin(admin.ModelAdmin):
    list_display = ("requester", "desired_date", "status")
    list_filter = ("status",)
