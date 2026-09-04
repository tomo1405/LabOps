"""優先度1: 研究支援系のビュー（詳細設計書 4章のエンドポイントに対応）。

参照範囲の方針:
- 研究日記は個人の記録なので、一覧・詳細は本人のみ参照できる。
- 研究スケジュールは「本人の予定 + 研究室共通予定（user=None）」を表示する。
- 学会準備は本人のものだけを表示・更新できる。
"""

import calendar
from datetime import date, datetime, time, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    ConferenceChecklistItemForm,
    ConferencePrepForm,
    DiaryEntryForm,
    ScheduleEventForm,
)
from .models import ConferenceChecklistItem, ConferencePrep, DiaryEntry, ScheduleEvent

DASHBOARD_DIARY_LIMIT = 5
DASHBOARD_EVENT_LIMIT = 5


def _visible_events(user):
    """本人の予定と研究室共通予定を対象とする QuerySet。"""
    return ScheduleEvent.objects.filter(Q(user=user) | Q(user__isnull=True))


# --- ダッシュボード -------------------------------------------------------


@login_required
@require_GET
def dashboard(request: HttpRequest) -> HttpResponse:
    """GET / : ダッシュボード（優先度1の情報を集約）。"""
    now = timezone.now()
    context = {
        "recent_diaries": DiaryEntry.objects.filter(user=request.user)[:DASHBOARD_DIARY_LIMIT],
        "upcoming_events": _visible_events(request.user)
        .filter(start_at__gte=now)
        .select_related("conference")[:DASHBOARD_EVENT_LIMIT],
        "conference_preps": ConferencePrep.objects.filter(user=request.user).prefetch_related(
            "checklist_items"
        ),
    }
    return render(request, "research/dashboard.html", context)


# --- 研究日記 -------------------------------------------------------------


@login_required
@require_GET
def diary_list(request: HttpRequest) -> HttpResponse:
    """GET /diary/ : 研究日記一覧（本人分）。タグでの絞り込みに対応。"""
    entries = DiaryEntry.objects.filter(user=request.user)
    tag = request.GET.get("tag", "").strip()
    if tag:
        entries = entries.filter(tags__icontains=tag)
    return render(request, "research/diary_list.html", {"entries": entries, "tag": tag})


@login_required
def diary_create(request: HttpRequest) -> HttpResponse:
    """GET/POST /diary/new : 研究日記の新規作成。"""
    if request.method == "POST":
        form = DiaryEntryForm(request.POST)
        if form.is_valid():
            entry = form.save(commit=False)
            entry.user = request.user
            entry.save()
            messages.success(request, "研究日記を保存しました。")
            return redirect("research:diary_detail", pk=entry.pk)
    else:
        form = DiaryEntryForm()
    return render(request, "research/diary_form.html", {"form": form})


@login_required
@require_GET
def diary_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """GET /diary/<id> : 研究日記詳細（本人分のみ）。"""
    entry = get_object_or_404(DiaryEntry, pk=pk, user=request.user)
    return render(request, "research/diary_detail.html", {"entry": entry})


# --- 研究スケジュール -----------------------------------------------------


def _month_range(year: int, month: int) -> tuple[date, date]:
    """指定月の初日と翌月初日（いずれもローカル日付）を返す。"""
    first = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    return first, first + timedelta(days=last_day)


def _as_local_start_of_day(day: date) -> datetime:
    """ローカルタイムゾーンでのその日の0時を aware datetime で返す。"""
    return timezone.make_aware(datetime.combine(day, time.min))


def _build_calendar(year: int, month: int, events) -> list[list[dict]]:
    """カレンダー表示用に「週 × 日」の構造を組み立てる。"""
    events_by_date: dict[date, list[ScheduleEvent]] = {}
    for event in events:
        key = timezone.localtime(event.start_at).date()
        events_by_date.setdefault(key, []).append(event)

    cal = calendar.Calendar(firstweekday=calendar.SUNDAY)
    today = timezone.localdate()
    weeks = []
    for week in cal.monthdatescalendar(year, month):
        weeks.append(
            [
                {
                    "date": day,
                    "in_month": day.month == month,
                    "is_today": day == today,
                    "events": events_by_date.get(day, []),
                }
                for day in week
            ]
        )
    return weeks


def _schedule_context(request: HttpRequest, year: int, month: int) -> dict:
    first, next_first = _month_range(year, month)
    events = list(
        _visible_events(request.user)
        .filter(
            start_at__gte=_as_local_start_of_day(first),
            start_at__lt=_as_local_start_of_day(next_first),
        )
        .select_related("user", "conference")
    )
    prev_month = first - timedelta(days=1)
    return {
        "year": year,
        "month": month,
        "weeks": _build_calendar(year, month, events),
        "events": events,
        "prev_year": prev_month.year,
        "prev_month": prev_month.month,
        "next_year": next_first.year,
        "next_month": next_first.month,
        "weekday_labels": ["日", "月", "火", "水", "木", "金", "土"],
    }


@login_required
@require_GET
def schedule_calendar(request: HttpRequest) -> HttpResponse:
    """GET /schedule/ : スケジュール（月次カレンダー）。"""
    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
    except ValueError as exc:
        raise Http404("年月の指定が不正です。") from exc
    if not 1 <= month <= 12:
        raise Http404("年月の指定が不正です。")

    context = _schedule_context(request, year, month)
    context["form"] = ScheduleEventForm(user=request.user)
    return render(request, "research/schedule.html", context)


@login_required
@require_POST
def schedule_event_create(request: HttpRequest) -> HttpResponse:
    """POST /schedule/events : 予定作成（htmx）。カレンダー部分のみ差し替える。"""
    form = ScheduleEventForm(request.POST, user=request.user)
    if form.is_valid():
        event = form.save(commit=False)
        # 共通予定フラグが付いていない限り、作成者を担当者にする
        if not request.POST.get("is_shared"):
            event.user = request.user
        else:
            event.user = None
        event.save()
        target = timezone.localtime(event.start_at).date()
        context = _schedule_context(request, target.year, target.month)
        context["form"] = ScheduleEventForm(user=request.user)
        context["created_event"] = event
        return render(request, "research/partials/schedule_calendar.html", context)

    today = timezone.localdate()
    context = _schedule_context(request, today.year, today.month)
    context["form"] = form
    return render(request, "research/partials/schedule_calendar.html", context, status=400)


# --- 学会準備 -------------------------------------------------------------


@login_required
@require_GET
def conference_list(request: HttpRequest) -> HttpResponse:
    """GET /conference/ : 学会準備一覧（締切・チェックリスト）。"""
    preps = ConferencePrep.objects.filter(user=request.user).prefetch_related("checklist_items")
    return render(
        request,
        "research/conference_list.html",
        {"preps": preps, "item_form": ConferenceChecklistItemForm()},
    )


@login_required
def conference_create(request: HttpRequest) -> HttpResponse:
    """GET/POST /conference/new : 学会準備の登録（詳細設計書 3.5 の手順1）。"""
    if request.method == "POST":
        form = ConferencePrepForm(request.POST)
        if form.is_valid():
            prep = form.save(commit=False)
            prep.user = request.user
            prep.save()
            ConferenceChecklistItem.objects.bulk_create(
                [
                    ConferenceChecklistItem(conference=prep, item=item)
                    for item in form.initial_checklist_items()
                ]
            )
            messages.success(request, "学会準備を登録しました。")
            return redirect("research:conference_list")
    else:
        form = ConferencePrepForm()
    return render(request, "research/conference_form.html", {"form": form})


@login_required
@require_POST
def checklist_item_toggle(request: HttpRequest, pk: int, item_id: int) -> HttpResponse:
    """POST /conference/<id>/checklist/<item_id>/toggle : チェック切替（htmx）。"""
    item = get_object_or_404(
        ConferenceChecklistItem,
        pk=item_id,
        conference_id=pk,
        conference__user=request.user,
    )
    item.done = not item.done
    item.save(update_fields=["done"])
    return render(request, "research/partials/checklist_item.html", {"item": item})


@login_required
@require_POST
def checklist_item_create(request: HttpRequest, pk: int) -> HttpResponse:
    """POST /conference/<id>/checklist : チェックリスト項目の追加（htmx）。"""
    prep = get_object_or_404(ConferencePrep, pk=pk, user=request.user)
    form = ConferenceChecklistItemForm(request.POST)
    if form.is_valid():
        item = form.save(commit=False)
        item.conference = prep
        item.save()
        status = 200
    else:
        status = 400
    return render(
        request,
        "research/partials/checklist.html",
        {"prep": prep, "item_form": ConferenceChecklistItemForm() if status == 200 else form},
        status=status,
    )
