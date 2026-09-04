"""ルーティング（詳細設計書 4章「画面・エンドポイント仕様」に対応）。"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("", include("research.urls")),
    path("", include("community.urls")),
]

# 開発サーバーでは添付ファイルをDjangoから配信する（本番は nginx が /media/ を配信）
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
