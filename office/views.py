"""優先度4: 事務系のビュー。

出張費申請は、承認画面が未実装のため、申請内容をメールで教員へ通知する。
申請自体はデータベースにも残すので、あとから一覧で確認できる。
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from research.models import ConferencePrep

from .forms import TravelExpenseRequestForm
from .mail import send_travel_expense_mail
from .models import TravelExpenseRequest


def _initial_from_conference(request: HttpRequest) -> dict:
    """学会準備ページから来た場合、その学会の情報を初期値にする。"""
    raw = request.GET.get("conference", "")
    if not raw.isdigit():
        return {}
    prep = ConferencePrep.objects.filter(pk=int(raw), user=request.user).first()
    if prep is None:
        return {}
    return {
        "destination": prep.conference_name,
        "purpose": f"{prep.conference_name} への参加のため",
    }


@login_required
def travel_expense_list(request: HttpRequest) -> HttpResponse:
    """GET/POST /travel-expenses/ : 出張費の申請と、自分の申請一覧。"""
    if request.method == "POST":
        form = TravelExpenseRequestForm(request.POST)
        if form.is_valid():
            expense = form.save(commit=False)
            expense.user = request.user
            expense.save()

            sent, reason = send_travel_expense_mail(expense)
            if sent:
                messages.success(request, "出張費を申請し、内容をメールで送信しました。")
            else:
                messages.warning(
                    request,
                    f"申請は保存しましたが、メールを送信できませんでした（{reason}）。"
                    "教員へ直接連絡してください。",
                )
            return redirect("office:travel_expense_list")
    else:
        form = TravelExpenseRequestForm(initial=_initial_from_conference(request))

    context = {
        "form": form,
        "requests": TravelExpenseRequest.objects.filter(user=request.user).select_related("approved_by"),
    }
    status = 400 if request.method == "POST" else 200
    return render(request, "office/travel_expense_list.html", context, status=status)
