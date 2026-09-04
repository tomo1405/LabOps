"""認証系ルーティング（詳細設計書 4章 /login）。"""

from django.contrib.auth import views as auth_views
from django.urls import path

app_name = "accounts"

urlpatterns = [
    path(
        "login",
        auth_views.LoginView.as_view(template_name="accounts/login.html", redirect_authenticated_user=True),
        name="login",
    ),
    path("logout", auth_views.LogoutView.as_view(), name="logout"),
]
