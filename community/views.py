"""優先度2: 情報共有・コミュニケーション系のビュー（詳細設計書 4章のエンドポイントに対応）。

参照範囲の方針:
- 在室状況・学食メニューは研究室全体の共有情報なので、全ログインユーザーが参照できる。
  更新できるのは自分の在室状態のみ。
- News記事は、公開済みは全員が参照でき、下書きは作成者本人だけが見える（詳細設計書 3.7）。
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import CanteenMenuForm, NewsPostForm
from .models import AttendanceStatus, CanteenMenu, MenuSource, NewsPost, NewsStatus

User = get_user_model()

CANTEEN_HISTORY_LIMIT = 7


# --- 在室メンバー可視化 ---------------------------------------------------


def _attendance_context(user) -> dict:
    """在室状況ボードの表示に必要なデータをまとめる。

    在室状況レコードを持たないメンバーも「不在」として一覧に並べる。
    """
    statuses = {s.user_id: s for s in AttendanceStatus.objects.select_related("user")}
    members = [
        {"user": member, "status": statuses.get(member.pk), "is_me": member.pk == user.pk}
        for member in User.objects.filter(is_active=True)
    ]
    return {
        "members": members,
        "present_count": sum(1 for m in members if m["status"] and m["status"].is_present),
        "my_status": statuses.get(user.pk),
    }


@login_required
@require_GET
def attendance_list(request: HttpRequest) -> HttpResponse:
    """GET /attendance/ : 在室メンバー一覧。"""
    return render(request, "community/attendance_list.html", _attendance_context(request.user))


@login_required
@require_POST
def attendance_toggle(request: HttpRequest) -> HttpResponse:
    """POST /attendance/toggle : 自分の在室状態を切り替える（htmx）。

    更新できるのは常にログインユーザー自身の状態に限る。
    """
    status, _ = AttendanceStatus.objects.get_or_create(user=request.user)
    status.toggle()
    return render(request, "community/partials/attendance_board.html", _attendance_context(request.user))


# --- 学食メニュー共有 -----------------------------------------------------


def _canteen_context(form: CanteenMenuForm | None = None) -> dict:
    today = timezone.localdate()
    return {
        "today": today,
        "today_menu": CanteenMenu.objects.filter(date=today).first(),
        "recent_menus": CanteenMenu.objects.exclude(date=today)[:CANTEEN_HISTORY_LIMIT],
        "form": form if form is not None else CanteenMenuForm(),
    }


@login_required
@require_GET
def canteen_today(request: HttpRequest) -> HttpResponse:
    """GET /canteen/today : 本日の学食メニューと直近の登録履歴。"""
    return render(request, "community/canteen.html", _canteen_context())


@login_required
@require_POST
def canteen_create(request: HttpRequest) -> HttpResponse:
    """POST /canteen/ : 学食メニューの登録。

    日付は一意（詳細設計書 2.9）なので、同じ日付の再登録は上書きとして扱う。
    """
    form = CanteenMenuForm(request.POST)
    if form.is_valid():
        menu, created = CanteenMenu.objects.update_or_create(
            date=form.cleaned_data["date"],
            defaults={"menu_text": form.cleaned_data["menu_text"], "source": MenuSource.MANUAL},
        )
        messages.success(request, f"{menu.date} のメニューを{'登録' if created else '更新'}しました。")
        return redirect("community:canteen_today")
    return render(request, "community/canteen.html", _canteen_context(form), status=400)


@login_required
def canteen_update(request: HttpRequest, pk: int) -> HttpResponse:
    """GET/POST /canteen/<id>/edit : 登録済みメニューの編集。

    日付ごとに1件のため、日付を既存の別日に変更した場合はその日を上書きする。
    """
    menu = get_object_or_404(CanteenMenu, pk=pk)
    if request.method == "POST":
        form = CanteenMenuForm(request.POST, instance=menu)
        if form.is_valid():
            date = form.cleaned_data["date"]
            # 別の日付へ移す場合、その日に既存の登録があれば上書きして重複を作らない
            CanteenMenu.objects.filter(date=date).exclude(pk=menu.pk).delete()
            menu.date = date
            menu.menu_text = form.cleaned_data["menu_text"]
            menu.source = MenuSource.MANUAL
            menu.save()
            messages.success(request, f"{menu.date} のメニューを更新しました。")
            return redirect("community:canteen_today")
    else:
        form = CanteenMenuForm(instance=menu)
    return render(request, "community/canteen_form.html", {"form": form, "menu": menu})


@login_required
def canteen_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """GET/POST /canteen/<id>/delete : 登録済みメニューの削除（GETは確認画面）。"""
    menu = get_object_or_404(CanteenMenu, pk=pk)
    if request.method == "POST":
        date = menu.date
        menu.delete()
        messages.success(request, f"{date} のメニューを削除しました。")
        return redirect("community:canteen_today")
    return render(request, "community/canteen_confirm_delete.html", {"menu": menu})


# --- 研究室HP News投稿 ----------------------------------------------------


def _visible_news(user):
    """公開済みの記事と、自分の下書きを対象とする QuerySet。"""
    return NewsPost.objects.filter(Q(status=NewsStatus.PUBLISHED) | Q(author=user)).select_related("author")


@login_required
@require_GET
def news_list(request: HttpRequest) -> HttpResponse:
    """GET /news/ : News一覧（公開済み + 自分の下書き）。"""
    posts = _visible_news(request.user)
    return render(request, "community/news_list.html", {"posts": posts})


@login_required
def news_create(request: HttpRequest) -> HttpResponse:
    """GET/POST /news/new : News投稿（詳細設計書 3.7 の手順1・2）。

    「下書き保存」と「公開」を同じフォームの送信ボタンで出し分ける。
    """
    if request.method == "POST":
        form = NewsPostForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.author = request.user
            post.save()
            if "publish" in request.POST:
                post.publish()
                messages.success(request, "News記事を公開しました。")
            else:
                messages.success(request, "News記事を下書き保存しました。")
            return redirect("community:news_list")
    else:
        form = NewsPostForm()
    return render(request, "community/news_form.html", {"form": form})


@login_required
def news_update(request: HttpRequest, pk: int) -> HttpResponse:
    """GET/POST /news/<id>/edit : News記事の編集（作成者のみ）。

    公開済みの記事を編集しても公開日時は変わらない（公開の取り下げは別操作）。
    """
    post = get_object_or_404(NewsPost, pk=pk, author=request.user)
    if request.method == "POST":
        form = NewsPostForm(request.POST, instance=post)
        if form.is_valid():
            form.save()
            messages.success(request, "News記事を更新しました。")
            return redirect("community:news_list")
    else:
        form = NewsPostForm(instance=post)
    return render(request, "community/news_form.html", {"form": form, "post": post})


@login_required
def news_delete(request: HttpRequest, pk: int) -> HttpResponse:
    """GET/POST /news/<id>/delete : News記事の削除（GETは確認画面）。"""
    post = get_object_or_404(NewsPost, pk=pk, author=request.user)
    if request.method == "POST":
        post.delete()
        messages.success(request, "News記事を削除しました。")
        return redirect("community:news_list")
    return render(request, "community/news_confirm_delete.html", {"post": post})


@login_required
@require_POST
def news_unpublish(request: HttpRequest, pk: int) -> HttpResponse:
    """POST /news/<id>/unpublish : 公開の取り下げ（作成者のみ）。

    研究室HPへの掲載対象から外したい場合に、下書きへ戻す。
    """
    post = get_object_or_404(NewsPost, pk=pk, author=request.user)
    post.unpublish()
    messages.success(request, f"「{post.title}」を下書きに戻しました。")
    return redirect("community:news_list")


@login_required
@require_POST
def news_publish(request: HttpRequest, pk: int) -> HttpResponse:
    """POST /news/<id>/publish : 下書きの公開（詳細設計書 3.7 の手順2）。

    公開できるのは自分が作成した記事のみ。
    """
    post = get_object_or_404(NewsPost, pk=pk, author=request.user)
    post.publish()
    messages.success(request, f"「{post.title}」を公開しました。")
    return redirect("community:news_list")
