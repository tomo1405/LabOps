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
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from community.models import AttendanceState, AttendanceStatus, CanteenMenu, NewsPost, NewsStatus

from .forms import (
    ConferenceChecklistItemForm,
    ConferencePrepForm,
    DiaryAttachmentForm,
    DiaryCommentForm,
    DiaryEntryForm,
    ScheduleEventForm,
)
from .models import (
    ConferenceChecklistItem,
    ConferencePrep,
    DiaryAttachment,
    DiaryComment,
    DiaryEntry,
    DiaryVisibility,
    ScheduleEvent,
)

DASHBOARD_DIARY_LIMIT = 5
DASHBOARD_EVENT_LIMIT = 5
DASHBOARD_NEWS_LIMIT = 3


def _visible_diaries(user):
    """本人の日記と、研究室内に公開された日記を対象とする QuerySet。"""
    return DiaryEntry.objects.filter(Q(user=user) | Q(visibility=DiaryVisibility.LAB)).select_related("user")


def _visible_events(user):
    """本人の予定と研究室共通予定を対象とする QuerySet。"""
    return ScheduleEvent.objects.filter(Q(user=user) | Q(user__isnull=True))


# --- ダッシュボード -------------------------------------------------------


@login_required
@require_GET
def dashboard(request: HttpRequest) -> HttpResponse:
    """GET / : ダッシュボード。

    基本設計書5章のとおり、研究支援（優先度1）の状況に加えて
    お知らせ（学食メニュー・研究室News）と在室メンバーを集約する。
    """
    now = timezone.now()
    present_statuses = AttendanceStatus.objects.filter(status=AttendanceState.PRESENT).select_related("user")
    context = {
        "recent_diaries": DiaryEntry.objects.filter(user=request.user)[:DASHBOARD_DIARY_LIMIT],
        "upcoming_events": _visible_events(request.user)
        .filter(start_at__gte=now)
        .select_related("conference")[:DASHBOARD_EVENT_LIMIT],
        "conference_preps": ConferencePrep.objects.filter(user=request.user).prefetch_related(
            "checklist_items"
        ),
        "present_members": [s.user for s in present_statuses],
        "today_menu": CanteenMenu.objects.filter(date=timezone.localdate()).first(),
        "latest_news": NewsPost.objects.filter(status=NewsStatus.PUBLISHED).select_related("author")[
            :DASHBOARD_NEWS_LIMIT
        ],
    }
    return render(request, "research/dashboard.html", context)


# --- 研究日記 -------------------------------------------------------------


@login_required
@require_GET
def diary_list(request: HttpRequest) -> HttpResponse:
    """GET /diary/ : 研究日記一覧。

    既定は自分の記録のみ。scope=lab で研究室内に公開された日記を一覧する。
    q= で本文・タグを対象にキーワード検索し、tag= でタグのみを対象に絞り込む。
    """
    scope = "lab" if request.GET.get("scope") == "lab" else "mine"
    if scope == "lab":
        entries = _visible_diaries(request.user).filter(visibility=DiaryVisibility.LAB)
    else:
        entries = DiaryEntry.objects.filter(user=request.user).select_related("user")

    # キーワード検索（本文・タグを対象）。空白区切りの語はすべて含むものに絞る（AND）
    query = request.GET.get("q", "").strip()
    if query:
        for word in query.split():
            entries = entries.filter(Q(content__icontains=word) | Q(tags__icontains=word))

    # タグバッジからの絞り込み（タグのみを対象）
    tag = request.GET.get("tag", "").strip()
    if tag:
        entries = entries.filter(tags__icontains=tag)

    return render(
        request,
        "research/diary_list.html",
        {"entries": entries, "query": query, "tag": tag, "scope": scope},
    )


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
    """GET /diary/<id> : 研究日記詳細。

    本人の記録に加えて、研究室内に公開された他メンバーの記録も閲覧できる。
    """
    entry = get_object_or_404(
        _visible_diaries(request.user).prefetch_related("attachments", "comments__author"), pk=pk
    )
    return render(
        request,
        "research/diary_detail.html",
        {
            "entry": entry,
            "attachment_form": DiaryAttachmentForm(),
            "comment_form": DiaryCommentForm(),
        },
    )


@login_required
def diary_update(request: HttpRequest, pk: int) -> HttpResponse:
    """GET/POST /diary/<id>/edit : 研究日記の編集（本人分のみ）。"""
    entry = get_object_or_404(DiaryEntry, pk=pk, user=request.user)
    if request.method == "POST":
        form = DiaryEntryForm(request.POST, instance=entry)
        if form.is_valid():
            form.save()
            messages.success(request, "研究日記を更新しました。")
            return redirect("research:diary_detail", pk=entry.pk)
    else:
        form = DiaryEntryForm(instance=entry)
    return render(request, "research/diary_form.html", {"form": form, "entry": entry})


@login_required
def diary_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """GET/POST /diary/<id>/delete : 研究日記の削除（本人分のみ）。

    GET は確認画面を表示し、POST で実際に削除する。
    """
    entry = get_object_or_404(DiaryEntry, pk=pk, user=request.user)
    if request.method == "POST":
        entry.delete()
        messages.success(request, "研究日記を削除しました。")
        return redirect("research:diary_list")
    return render(request, "research/diary_confirm_delete.html", {"entry": entry})


@login_required
@require_POST
def diary_attachment_create(request: HttpRequest, pk: int) -> HttpResponse:
    """POST /diary/<id>/attachments : 添付ファイルの追加（本人の日記のみ）。"""
    entry = get_object_or_404(DiaryEntry, pk=pk, user=request.user)
    form = DiaryAttachmentForm(request.POST, request.FILES)
    if form.is_valid():
        attachment = form.save(commit=False)
        attachment.diary = entry
        attachment.original_name = request.FILES["file"].name
        attachment.save()
        messages.success(request, f"「{attachment.original_name}」を添付しました。")
        return redirect("research:diary_detail", pk=entry.pk)

    entry = _visible_diaries(request.user).prefetch_related("attachments").get(pk=entry.pk)
    return render(
        request,
        "research/diary_detail.html",
        {"entry": entry, "attachment_form": form},
        status=400,
    )


@login_required
@require_POST
def diary_attachment_delete(request: HttpRequest, pk: int, attachment_id: int) -> HttpResponse:
    """POST /diary/<id>/attachments/<attachment_id>/delete : 添付の削除。"""
    attachment = get_object_or_404(DiaryAttachment, pk=attachment_id, diary_id=pk, diary__user=request.user)
    name = attachment.original_name
    # 実ファイルも消す（save=False でDB更新は delete() に任せる）
    attachment.file.delete(save=False)
    attachment.delete()
    messages.success(request, f"「{name}」を削除しました。")
    return redirect("research:diary_detail", pk=pk)


@login_required
@require_POST
def diary_comment_create(request: HttpRequest, pk: int) -> HttpResponse:
    """POST /diary/<id>/comments : コメントの投稿。

    閲覧できる日記（自分のもの、または研究室内に公開された日記）にだけ投稿できる。
    """
    entry = get_object_or_404(_visible_diaries(request.user), pk=pk)
    form = DiaryCommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.diary = entry
        comment.author = request.user
        comment.save()
        messages.success(request, "コメントを投稿しました。")
        return redirect("research:diary_detail", pk=entry.pk)

    entry = (
        _visible_diaries(request.user).prefetch_related("attachments", "comments__author").get(pk=entry.pk)
    )
    return render(
        request,
        "research/diary_detail.html",
        {"entry": entry, "attachment_form": DiaryAttachmentForm(), "comment_form": form},
        status=400,
    )


@login_required
@require_POST
def diary_comment_delete(request: HttpRequest, pk: int, comment_id: int) -> HttpResponse:
    """POST /diary/<id>/comments/<comment_id>/delete : コメントの削除。

    コメントの投稿者に加えて、日記の作成者も削除できる。
    """
    comment = get_object_or_404(
        DiaryComment.objects.filter(Q(author=request.user) | Q(diary__user=request.user)),
        pk=comment_id,
        diary_id=pk,
    )
    comment.delete()
    messages.success(request, "コメントを削除しました。")
    return redirect("research:diary_detail", pk=pk)


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


def _schedule_url_for(event: ScheduleEvent) -> str:
    """その予定が属する月のカレンダーURLを返す。"""
    target = timezone.localtime(event.start_at).date()
    return f"{reverse('research:schedule')}?year={target.year}&month={target.month}"


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


def _editable_event(request: HttpRequest, pk: int) -> ScheduleEvent:
    """編集・削除できる予定を取得する。

    本人の予定に加えて、研究室共通の予定（担当者なし）も対象とする。
    共通予定は誰でも作成できる設計のため、編集・削除も全メンバーに開いている。
    """
    return get_object_or_404(_visible_events(request.user), pk=pk)


@login_required
def schedule_event_update(request: HttpRequest, pk: int) -> HttpResponse:
    """GET/POST /schedule/events/<id>/edit : 予定の編集。"""
    event = _editable_event(request, pk)
    if request.method == "POST":
        form = ScheduleEventForm(request.POST, instance=event, user=request.user)
        if form.is_valid():
            updated = form.save(commit=False)
            updated.user = None if request.POST.get("is_shared") else request.user
            updated.save()
            messages.success(request, "予定を更新しました。")
            return redirect(_schedule_url_for(updated))
    else:
        form = ScheduleEventForm(instance=event, user=request.user)
    return render(
        request,
        "research/schedule_form.html",
        {"form": form, "event": event, "is_shared": event.is_shared},
    )


@login_required
def schedule_event_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """GET/POST /schedule/events/<id>/delete : 予定の削除（GETは確認画面）。"""
    event = _editable_event(request, pk)
    if request.method == "POST":
        redirect_to = _schedule_url_for(event)
        event.delete()
        messages.success(request, "予定を削除しました。")
        return redirect(redirect_to)
    return render(request, "research/schedule_confirm_delete.html", {"event": event})


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
def conference_update(request: HttpRequest, pk: int) -> HttpResponse:
    """GET/POST /conference/<id>/edit : 学会名・締切日の編集（本人分のみ）。

    チェックリストは一覧画面から個別に追加・削除するため、このフォームでは扱わない。
    """
    prep = get_object_or_404(ConferencePrep, pk=pk, user=request.user)
    if request.method == "POST":
        form = ConferencePrepForm(request.POST, instance=prep)
        if form.is_valid():
            form.save()
            ConferenceChecklistItem.objects.bulk_create(
                [
                    ConferenceChecklistItem(conference=prep, item=item)
                    for item in form.initial_checklist_items()
                ]
            )
            messages.success(request, "学会準備を更新しました。")
            return redirect("research:conference_list")
    else:
        form = ConferencePrepForm(instance=prep)
    return render(request, "research/conference_form.html", {"form": form, "prep": prep})


@login_required
def conference_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """GET/POST /conference/<id>/delete : 学会準備の削除（GETは確認画面）。

    チェックリスト項目も一緒に削除される。
    """
    prep = get_object_or_404(ConferencePrep, pk=pk, user=request.user)
    if request.method == "POST":
        prep.delete()
        messages.success(request, "学会準備を削除しました。")
        return redirect("research:conference_list")
    return render(request, "research/conference_confirm_delete.html", {"prep": prep})


@login_required
@require_POST
def checklist_item_delete(request: HttpRequest, pk: int, item_id: int) -> HttpResponse:
    """POST /conference/<id>/checklist/<item_id>/delete : チェック項目の削除（htmx）。"""
    item = get_object_or_404(
        ConferenceChecklistItem, pk=item_id, conference_id=pk, conference__user=request.user
    )
    prep = item.conference
    item.delete()
    return render(
        request,
        "research/partials/checklist.html",
        {"prep": prep, "item_form": ConferenceChecklistItemForm()},
    )


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
