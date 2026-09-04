"""優先度2: 情報共有・コミュニケーション系のルーティング（詳細設計書 4章）。"""

from django.urls import path

from . import views

app_name = "community"

urlpatterns = [
    # 在室メンバー可視化
    path("attendance/", views.attendance_list, name="attendance_list"),
    path("attendance/toggle", views.attendance_toggle, name="attendance_toggle"),
    # 学食メニュー共有
    path("canteen/today", views.canteen_today, name="canteen_today"),
    path("canteen/", views.canteen_create, name="canteen_create"),
    # 研究室HP News投稿
    path("news/", views.news_list, name="news_list"),
    path("news/new", views.news_create, name="news_create"),
    # 詳細設計書3.7の「公開操作」に対応するため、設計書の一覧に追加した経路
    path("news/<int:pk>/publish", views.news_publish, name="news_publish"),
    path("news/<int:pk>/unpublish", views.news_unpublish, name="news_unpublish"),
    path("news/<int:pk>/edit", views.news_update, name="news_update"),
    path("news/<int:pk>/delete", views.news_delete, name="news_delete"),
]
