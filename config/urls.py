"""ルーティング（詳細設計書 4章「画面・エンドポイント仕様」に対応）。"""

from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import include, path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    # 使い方ページ。特定の機能に属さないため、プロジェクト側で直接ルーティングする
    path(
        "guide/",
        login_required(TemplateView.as_view(template_name="guide.html")),
        name="guide",
    ),
    path("", include("accounts.urls")),
    path("", include("research.urls")),
    path("", include("community.urls")),
]

# 添付ファイル（MEDIA_ROOT）はここで公開しない。
# 非公開日記の添付が権限なしで取得されるのを防ぐため、開発・本番ともに
# 認可付きビュー research:diary_attachment_download 経由でのみ配信する。
