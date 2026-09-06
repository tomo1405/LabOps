"""優先度4: 事務系のルーティング（詳細設計書 4章）。"""

from django.urls import path

from . import views

app_name = "office"

urlpatterns = [
    path("travel-expenses/", views.travel_expense_list, name="travel_expense_list"),
]
