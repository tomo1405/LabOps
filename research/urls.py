"""優先度1: 研究支援系のルーティング（詳細設計書 4章）。"""

from django.urls import path

from . import views

app_name = "research"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    # 研究日記
    path("diary/", views.diary_list, name="diary_list"),
    path("diary/new", views.diary_create, name="diary_create"),
    path("diary/<int:pk>", views.diary_detail, name="diary_detail"),
    path("diary/<int:pk>/edit", views.diary_update, name="diary_update"),
    path("diary/<int:pk>/delete", views.diary_delete, name="diary_delete"),
    path("diary/<int:pk>/attachments", views.diary_attachment_create, name="diary_attachment_create"),
    path(
        "diary/<int:pk>/attachments/<int:attachment_id>/file",
        views.diary_attachment_download,
        name="diary_attachment_download",
    ),
    path(
        "diary/<int:pk>/attachments/<int:attachment_id>/delete",
        views.diary_attachment_delete,
        name="diary_attachment_delete",
    ),
    path("diary/<int:pk>/comments", views.diary_comment_create, name="diary_comment_create"),
    path(
        "diary/<int:pk>/comments/<int:comment_id>/delete",
        views.diary_comment_delete,
        name="diary_comment_delete",
    ),
    # 研究スケジュール
    path("schedule/", views.schedule_calendar, name="schedule"),
    path("schedule/events", views.schedule_event_create, name="schedule_event_create"),
    path("schedule/events/<int:pk>/edit", views.schedule_event_update, name="schedule_event_update"),
    path("schedule/events/<int:pk>/delete", views.schedule_event_delete, name="schedule_event_delete"),
    # 学会準備
    path("conference/", views.conference_list, name="conference_list"),
    path("conference/new", views.conference_create, name="conference_create"),
    path("conference/<int:pk>/edit", views.conference_update, name="conference_update"),
    path("conference/<int:pk>/delete", views.conference_delete, name="conference_delete"),
    path("conference/<int:pk>/checklist", views.checklist_item_create, name="checklist_item_create"),
    path(
        "conference/<int:pk>/checklist/<int:item_id>/toggle",
        views.checklist_item_toggle,
        name="checklist_item_toggle",
    ),
    path(
        "conference/<int:pk>/checklist/<int:item_id>/delete",
        views.checklist_item_delete,
        name="checklist_item_delete",
    ),
]
