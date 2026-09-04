"""優先度1: 研究支援系のモデル（詳細設計書 2.3〜2.5）。"""

from html import unescape

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

from .markdown_render import render_markdown


class DiaryVisibility(models.TextChoices):
    PRIVATE = "private", "非公開（自分のみ）"
    LAB = "lab", "研究室内に公開"


class DiaryEntry(models.Model):
    """研究日記（詳細設計書 2.3 DiaryEntry）。

    公開範囲（visibility）は設計書にない追加項目。既定は非公開で、
    本人が明示的に切り替えたものだけを研究室内へ公開する。
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="diary_entries",
        verbose_name="作成者",
    )
    date = models.DateField("日付")
    content = models.TextField("本文")
    tags = models.CharField("タグ", max_length=200, blank=True, help_text="カンマ区切りで入力")
    visibility = models.CharField(
        "公開範囲",
        max_length=10,
        choices=DiaryVisibility.choices,
        default=DiaryVisibility.PRIVATE,
        help_text="研究室内に公開すると、他のメンバーも閲覧できます",
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "研究日記"
        verbose_name_plural = "研究日記"
        ordering = ["-date", "-created_at"]
        indexes = [models.Index(fields=["user", "-date"])]

    def __str__(self) -> str:
        return f"{self.date} {self.user.name}"

    def tag_list(self) -> list[str]:
        """カンマ区切りタグをリスト化する（空要素は除去）。"""
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    @property
    def is_public(self) -> bool:
        """研究室内に公開されているか。"""
        return self.visibility == DiaryVisibility.LAB

    @property
    def content_excerpt(self) -> str:
        """一覧に出す抜粋。Markdownの記法を除いた本文の先頭部分。"""
        text = strip_tags(render_markdown(self.content)).replace("\n", " ").strip()
        return unescape(text)

    @property
    def content_html(self) -> str:
        """本文をMarkdownとして描画したHTML（サニタイズ済み）。"""
        return mark_safe(render_markdown(self.content))  # noqa: S308 — render_markdown でサニタイズ済み


def diary_attachment_path(instance: "DiaryAttachment", filename: str) -> str:
    """添付ファイルの保存先。日記ごとにディレクトリを分ける。"""
    return f"diary/{instance.diary_id}/{filename}"


class DiaryAttachment(models.Model):
    """研究日記の添付ファイル（実験画像・グラフ・資料など）。

    詳細設計書2.3にない追加テーブル。日記1件に複数添付できる。
    """

    IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp")

    diary = models.ForeignKey(
        DiaryEntry,
        on_delete=models.CASCADE,
        related_name="attachments",
        verbose_name="研究日記",
    )
    file = models.FileField("ファイル", upload_to=diary_attachment_path)
    original_name = models.CharField("元のファイル名", max_length=255)
    uploaded_at = models.DateTimeField("添付日時", auto_now_add=True)

    class Meta:
        verbose_name = "研究日記の添付ファイル"
        verbose_name_plural = "研究日記の添付ファイル"
        ordering = ["uploaded_at", "id"]

    def __str__(self) -> str:
        return self.original_name

    @property
    def is_image(self) -> bool:
        """画像として画面に埋め込めるか。"""
        return self.original_name.lower().endswith(self.IMAGE_SUFFIXES)


class DiaryComment(models.Model):
    """研究日記へのコメント。

    詳細設計書2.3にない追加テーブル。公開された日記に対して
    研究室メンバーが助言や質問を書けるようにする。
    """

    diary = models.ForeignKey(
        DiaryEntry,
        on_delete=models.CASCADE,
        related_name="comments",
        verbose_name="研究日記",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="diary_comments",
        verbose_name="投稿者",
    )
    body = models.TextField("本文")
    created_at = models.DateTimeField("投稿日時", auto_now_add=True)

    class Meta:
        verbose_name = "研究日記のコメント"
        verbose_name_plural = "研究日記のコメント"
        ordering = ["created_at", "id"]

    def __str__(self) -> str:
        return f"{self.author.name}: {self.body[:20]}"


class ConferencePrep(models.Model):
    """学会準備（詳細設計書 2.5 ConferencePrep）。"""

    DEADLINE_WARNING_DAYS = 14

    conference_name = models.CharField("学会名", max_length=100)
    deadline = models.DateField("締切日")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="conference_preps",
        verbose_name="担当者",
    )

    class Meta:
        verbose_name = "学会準備"
        verbose_name_plural = "学会準備"
        ordering = ["deadline"]

    def __str__(self) -> str:
        return f"{self.conference_name}（締切 {self.deadline}）"

    @property
    def days_until_deadline(self) -> int:
        """締切までの残日数。締切を過ぎている場合は負数。"""
        return (self.deadline - timezone.localdate()).days

    @property
    def is_deadline_near(self) -> bool:
        """締切が近い（未経過かつ残り DEADLINE_WARNING_DAYS 日以内）か。

        詳細設計書 3.5 の「締切が近づいた項目は強調表示」の判定に使用する。
        """
        return 0 <= self.days_until_deadline <= self.DEADLINE_WARNING_DAYS

    @property
    def is_overdue(self) -> bool:
        """締切を過ぎているか。"""
        return self.days_until_deadline < 0

    @property
    def progress_percent(self) -> int:
        """チェックリストの完了率（項目が無い場合は0）。"""
        items = list(self.checklist_items.all())
        if not items:
            return 0
        done = sum(1 for item in items if item.done)
        return round(done * 100 / len(items))


class ConferenceChecklistItem(models.Model):
    """学会準備チェックリスト項目（詳細設計書 2.5 子テーブル）。"""

    conference = models.ForeignKey(
        ConferencePrep,
        on_delete=models.CASCADE,
        related_name="checklist_items",
        verbose_name="学会準備",
    )
    item = models.CharField("項目", max_length=200)
    done = models.BooleanField("完了", default=False)

    class Meta:
        verbose_name = "学会準備チェックリスト項目"
        verbose_name_plural = "学会準備チェックリスト項目"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.item}{'（完了）' if self.done else ''}"


class EventType(models.TextChoices):
    MILESTONE = "milestone", "マイルストーン"
    TASK = "task", "タスク"


class ScheduleEvent(models.Model):
    """研究スケジュール（詳細設計書 2.4 ScheduleEvent）。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="schedule_events",
        verbose_name="担当者",
        help_text="空欄の場合は研究室共通の予定として扱う",
    )
    title = models.CharField("タイトル", max_length=100)
    start_at = models.DateTimeField("開始日時")
    end_at = models.DateTimeField("終了日時", null=True, blank=True)
    event_type = models.CharField("種別", max_length=10, choices=EventType.choices)
    conference = models.ForeignKey(
        ConferencePrep,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedule_events",
        verbose_name="関連する学会準備",
    )

    class Meta:
        verbose_name = "研究スケジュール"
        verbose_name_plural = "研究スケジュール"
        ordering = ["start_at"]
        indexes = [models.Index(fields=["start_at"])]

    def __str__(self) -> str:
        return f"{timezone.localtime(self.start_at):%Y-%m-%d %H:%M} {self.title}"

    @property
    def is_shared(self) -> bool:
        """研究室共通の予定（担当者なし）か。"""
        return self.user_id is None
