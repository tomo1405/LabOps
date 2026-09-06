"""優先度1: 研究支援系のビュー（詳細設計書 4章のエンドポイントに対応）。

参照範囲の方針:
- 研究日記は個人の記録なので、一覧・詳細は本人のみ参照できる。
- 研究スケジュールは「本人の予定 + 研究室共通予定（user=None）」を表示する。
- 学会準備は本人のものだけを表示・更新できる。
"""

import calendar
from datetime import date, datetime, time, timedelta
from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from community.models import AttendanceState, AttendanceStatus, CanteenMenu, NewsPost, NewsStatus

from . import attachments as attachment_types
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
    return (
        DiaryEntry.objects.filter(Q(user=user) | Q(visibility=DiaryVisibility.LAB))
        .select_related("user")
        .prefetch_related("likes")
    )


def _visible_events(user):
    """本人の予定・研究室共通予定・自分が参加者に入っている予定を対象とする QuerySet。"""
    return ScheduleEvent.objects.filter(Q(user=user) | Q(user__isnull=True) | Q(participants=user)).distinct()


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
        entries = (
            DiaryEntry.objects.filter(user=request.user).select_related("user").prefetch_related("likes")
        )

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
            "liked": entry.is_liked_by(request.user),
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
def diary_like_toggle(request: HttpRequest, pk: int) -> HttpResponse:
    """POST /diary/<id>/like : いいねの付け外し（htmx）。

    閲覧できる日記（自分のもの、または研究室内に公開された日記）にだけ付けられる。
    """
    entry = get_object_or_404(_visible_diaries(request.user), pk=pk)
    entry.toggle_like(request.user)
    return render(
        request,
        "research/partials/diary_like.html",
        {"entry": entry, "liked": entry.is_liked_by(request.user)},
    )


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

    # 通常の詳細表示と同じコンテキストで再描画する。
    # comment_form を省くと、添付エラー後だけコメント欄が消えてしまう。
    entry = (
        _visible_diaries(request.user).prefetch_related("attachments", "comments__author").get(pk=entry.pk)
    )
    return render(
        request,
        "research/diary_detail.html",
        {"entry": entry, "attachment_form": form, "comment_form": DiaryCommentForm()},
        status=400,
    )


@login_required
@require_POST
def diary_attachment_delete(request: HttpRequest, pk: int, attachment_id: int) -> HttpResponse:
    """POST /diary/<id>/attachments/<attachment_id>/delete : 添付の削除。"""
    attachment = get_object_or_404(DiaryAttachment, pk=attachment_id, diary_id=pk, diary__user=request.user)
    name = attachment.original_name
    # 実体の削除は post_delete シグナル（research/signals.py）が行う
    attachment.delete()
    messages.success(request, f"「{name}」を削除しました。")
    return redirect("research:diary_detail", pk=pk)


@login_required
@require_GET
def diary_attachment_download(request: HttpRequest, pk: int, attachment_id: int) -> HttpResponse:
    """GET /diary/<id>/attachments/<attachment_id>/file : 添付ファイルの配信。

    実体は nginx から直接配信させず、必ずここで認可を判定する。
    - ログイン済みであること（login_required）
    - 日記が本人のもの、または研究室内に公開されていること
    - 添付がURLの日記に属していること
    を満たさない場合は404を返す。
    """
    attachment = get_object_or_404(
        DiaryAttachment.objects.filter(diary__in=_visible_diaries(request.user)),
        pk=attachment_id,
        diary_id=pk,
    )
    content_type = attachment.content_type
    # 画像だけ画面に埋め込む。それ以外は同一オリジンでの実行を防ぐため必ずダウンロードさせる
    disposition = "inline" if attachment.is_image else "attachment"
    filename = attachment_types.safe_original_name(attachment.original_name)

    if getattr(settings, "USE_X_ACCEL_REDIRECT", False):
        # 認可判定後の実体配信は nginx（internal な /media/）に任せる
        response = HttpResponse(content_type=content_type)
        response["X-Accel-Redirect"] = settings.MEDIA_URL + quote(attachment.file.name)
        response["Content-Disposition"] = f"{disposition}; filename*=UTF-8''{quote(filename)}"
    else:
        response = FileResponse(
            attachment.file.open("rb"),
            content_type=content_type,
            as_attachment=not attachment.is_image,
            filename=filename,
        )
    # 拡張子から決めた Content-Type を、ブラウザに推測で上書きさせない
    response["X-Content-Type-Options"] = "nosniff"
    return response


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


SCHEDULE_VIEWS = ("month", "week", "day")
WEEKDAY_LABELS = ["日", "月", "火", "水", "木", "金", "土"]


def _as_local_start_of_day(day: date) -> datetime:
    """ローカルタイムゾーンでのその日の0時を aware datetime で返す。"""
    return timezone.make_aware(datetime.combine(day, time.min))


def _weekday_label(day: date) -> str:
    """日曜始まりの曜日ラベル。"""
    return WEEKDAY_LABELS[(day.weekday() + 1) % 7]


def _week_start(day: date) -> date:
    """その日を含む週の日曜日を返す（カレンダーの週始まりに合わせる）。"""
    return day - timedelta(days=(day.weekday() + 1) % 7)


def _period_range(view: str, anchor: date) -> tuple[date, date]:
    """表示単位ごとの [開始日, 終了日) を返す。"""
    if view == "day":
        return anchor, anchor + timedelta(days=1)
    if view == "week":
        start = _week_start(anchor)
        return start, start + timedelta(days=7)
    first = anchor.replace(day=1)
    return first, first + timedelta(days=calendar.monthrange(first.year, first.month)[1])


def _shift_anchor(view: str, anchor: date, direction: int) -> date:
    """前後の期間の基準日を返す。"""
    if view == "day":
        return anchor + timedelta(days=direction)
    if view == "week":
        return anchor + timedelta(days=7 * direction)
    first = anchor.replace(day=1)
    if direction < 0:
        return (first - timedelta(days=1)).replace(day=1)
    return first + timedelta(days=calendar.monthrange(first.year, first.month)[1])


def _period_label(view: str, anchor: date) -> str:
    """画面上部に出す期間の見出し。"""
    if view == "day":
        return f"{anchor.year}年{anchor.month}月{anchor.day}日（{_weekday_label(anchor)}）"
    if view == "week":
        start, end = _period_range(view, anchor)
        last = end - timedelta(days=1)
        if start.month == last.month:
            return f"{start.year}年{start.month}月{start.day}日 〜 {last.day}日"
        return f"{start.year}年{start.month}月{start.day}日 〜 {last.month}月{last.day}日"
    return f"{anchor.year}年{anchor.month}月"


def _schedule_url(view: str, anchor: date) -> str:
    return f"{reverse('research:schedule')}?view={view}&date={anchor.isoformat()}"


def _events_by_date(events) -> dict:
    grouped: dict = {}
    for event in events:
        grouped.setdefault(timezone.localtime(event.start_at).date(), []).append(event)
    return grouped


def _build_month_weeks(anchor: date, grouped: dict, today: date) -> list:
    """月表示用に「週 × 日」の構造を組み立てる。"""
    cal = calendar.Calendar(firstweekday=calendar.SUNDAY)
    return [
        [
            {
                "date": day,
                "in_month": day.month == anchor.month,
                "is_today": day == today,
                "events": grouped.get(day, []),
                "url": _schedule_url("day", day),
            }
            for day in week
        ]
        for week in cal.monthdatescalendar(anchor.year, anchor.month)
    ]


def _build_days(start: date, count: int, grouped: dict, today: date) -> list:
    """週・日表示用に、日ごとの予定をまとめる。"""
    days = []
    for offset in range(count):
        day = start + timedelta(days=offset)
        days.append(
            {
                "date": day,
                "weekday": _weekday_label(day),
                "is_today": day == today,
                "events": grouped.get(day, []),
                "url": _schedule_url("day", day),
            }
        )
    return days


def _schedule_context(request: HttpRequest, view: str, anchor: date) -> dict:
    start, end = _period_range(view, anchor)
    events = list(
        _visible_events(request.user)
        .filter(
            start_at__gte=_as_local_start_of_day(start),
            start_at__lt=_as_local_start_of_day(end),
        )
        .select_related("user", "conference")
        .prefetch_related("participants")
    )
    grouped = _events_by_date(events)
    today = timezone.localdate()

    context = {
        "view": view,
        "anchor": anchor,
        "events": events,
        "period_label": _period_label(view, anchor),
        "prev_url": _schedule_url(view, _shift_anchor(view, anchor, -1)),
        "next_url": _schedule_url(view, _shift_anchor(view, anchor, 1)),
        "today_url": _schedule_url(view, today),
        "month_url": _schedule_url("month", anchor),
        "week_url": _schedule_url("week", anchor),
        "day_url": _schedule_url("day", anchor),
        "weekday_labels": WEEKDAY_LABELS,
    }
    if view == "month":
        context["weeks"] = _build_month_weeks(anchor, grouped, today)
    elif view == "week":
        context["days"] = _build_days(start, 7, grouped, today)
    else:
        context["days"] = _build_days(start, 1, grouped, today)
    return context


def _schedule_url_for(event: ScheduleEvent, view: str = "month") -> str:
    """その予定が含まれる期間のカレンダーURLを返す。"""
    return _schedule_url(view, timezone.localtime(event.start_at).date())


def _requested_view(request: HttpRequest) -> str:
    view = request.GET.get("view") or request.POST.get("view") or "month"
    return view if view in SCHEDULE_VIEWS else "month"


def _requested_anchor(request: HttpRequest) -> date:
    """表示の基準日。date= を優先し、旧来の year/month 指定にも対応する。"""
    raw = request.GET.get("date") or request.POST.get("date")
    if raw:
        try:
            return date.fromisoformat(raw)
        except ValueError as exc:
            raise Http404("日付の指定が不正です。") from exc

    today = timezone.localdate()
    if "year" in request.GET or "month" in request.GET:
        try:
            year = int(request.GET.get("year", today.year))
            month = int(request.GET.get("month", today.month))
            return date(year, month, 1)
        except ValueError as exc:
            raise Http404("年月の指定が不正です。") from exc
    return today


@login_required
@require_GET
def schedule_calendar(request: HttpRequest) -> HttpResponse:
    """GET /schedule/ : スケジュール。view=month|week|day で表示単位を切り替える。"""
    view = _requested_view(request)
    anchor = _requested_anchor(request)
    context = _schedule_context(request, view, anchor)
    context["form"] = ScheduleEventForm(user=request.user)
    return render(request, "research/schedule.html", context)


@login_required
@require_POST
def schedule_event_create(request: HttpRequest) -> HttpResponse:
    """POST /schedule/events : 予定作成（htmx）。表示中の単位のまま差し替える。"""
    view = _requested_view(request)
    form = ScheduleEventForm(request.POST, user=request.user)
    if form.is_valid():
        event = form.save(commit=False)
        # 共通予定フラグが付いていない限り、作成者を担当者にする
        event.user = None if request.POST.get("is_shared") else request.user
        event.save()
        form.save_m2m()
        target = timezone.localtime(event.start_at).date()
        context = _schedule_context(request, view, target)
        context["form"] = ScheduleEventForm(user=request.user)
        context["created_event"] = event
        return render(request, "research/partials/schedule_calendar.html", context)

    context = _schedule_context(request, view, _requested_anchor(request))
    context["form"] = form
    return render(request, "research/partials/schedule_calendar.html", context, status=400)


def _editable_event(request: HttpRequest, pk: int) -> ScheduleEvent:
    """編集・削除できる予定を取得する。

    本人の予定と研究室共通の予定（担当者なし）が対象。
    参加者として追加されただけの人は、他人の予定を書き換えられない。
    """
    return get_object_or_404(ScheduleEvent.objects.filter(Q(user=request.user) | Q(user__isnull=True)), pk=pk)


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
            form.save_m2m()
            messages.success(request, "予定を更新しました。")
            return redirect(_schedule_url_for(updated, _requested_view(request)))
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
        redirect_to = _schedule_url_for(event, _requested_view(request))
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
            # 学会準備だけが保存された状態を残さないよう、両方まとめて確定させる
            with transaction.atomic():
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
            # 学会名・締切日の変更だけが残る部分更新を避ける
            with transaction.atomic():
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
        "research/partials/checklist_response.html",
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
    return render(request, "research/partials/checklist_item_response.html", {"item": item})


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
        "research/partials/checklist_response.html",
        {"prep": prep, "item_form": ConferenceChecklistItemForm() if status == 200 else form},
        status=status,
    )
