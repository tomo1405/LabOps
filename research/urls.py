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
    # 研究スケジュール
    path("schedule/", views.schedule_calendar, name="schedule"),
    path("schedule/events", views.schedule_event_create, name="schedule_event_create"),
    # 学会準備
    path("conference/", views.conference_list, name="conference_list"),
    path("conference/new", views.conference_create, name="conference_create"),
    path("conference/<int:pk>/checklist", views.checklist_item_create, name="checklist_item_create"),
    path(
        "conference/<int:pk>/checklist/<int:item_id>/toggle",
        views.checklist_item_toggle,
        name="checklist_item_toggle",
    ),
]
