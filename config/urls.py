"""ルーティング（詳細設計書 4章「画面・エンドポイント仕様」に対応）。"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("research.urls")),
    path("", include("community.urls")),
]
