"""優先度2: 情報共有・コミュニケーション系のモデル（詳細設計書 2.2 / 2.9 / 2.10）。"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class AttendanceState(models.TextChoices):
    PRESENT = "present", "在室"
    ABSENT = "absent", "不在"


class AttendanceStatus(models.Model):
    """在室状況（詳細設計書 2.2 AttendanceStatus）。"""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_status",
        verbose_name="ユーザー",
    )
    status = models.CharField(
        "状態", max_length=10, choices=AttendanceState.choices, default=AttendanceState.ABSENT
    )
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "在室状況"
        verbose_name_plural = "在室状況"

    def __str__(self) -> str:
        return f"{self.user.name}: {self.get_status_display()}"

    @property
    def is_present(self) -> bool:
        return self.status == AttendanceState.PRESENT

    def toggle(self) -> "AttendanceStatus":
        """在室／不在を反転して保存する（詳細設計書 4章 /attendance/toggle）。"""
        self.status = AttendanceState.ABSENT if self.is_present else AttendanceState.PRESENT
        self.save(update_fields=["status", "updated_at"])
        return self


class MenuSource(models.TextChoices):
    MANUAL = "manual", "手動登録"
    SCRAPED = "scraped", "自動取得"


class CanteenMenu(models.Model):
    """学食メニュー（詳細設計書 2.9 CanteenMenu）。"""

    date = models.DateField("日付", unique=True)
    menu_text = models.TextField("メニュー内容")
    source = models.CharField("取得元", max_length=10, choices=MenuSource.choices, default=MenuSource.MANUAL)

    class Meta:
        verbose_name = "学食メニュー"
        verbose_name_plural = "学食メニュー"
        ordering = ["-date"]

    def __str__(self) -> str:
        return f"{self.date} の学食メニュー"


class NewsStatus(models.TextChoices):
    DRAFT = "draft", "下書き"
    PUBLISHED = "published", "公開"


class NewsPost(models.Model):
    """研究室HP News投稿（詳細設計書 2.10 NewsPost）。"""

    title = models.CharField("タイトル", max_length=200)
    body = models.TextField("本文")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="news_posts",
        verbose_name="投稿者",
    )
    status = models.CharField(
        "ステータス", max_length=10, choices=NewsStatus.choices, default=NewsStatus.DRAFT
    )
    published_at = models.DateTimeField("公開日時", null=True, blank=True)

    class Meta:
        verbose_name = "News記事"
        verbose_name_plural = "News記事"
        # 公開日時の新しい順。未公開（published_at が NULL）の下書きは先頭に置く。
        # NULL の並び位置は PostgreSQL と SQLite で既定が逆になるため、明示的に指定する。
        ordering = [models.F("published_at").desc(nulls_first=True), "-id"]

    def __str__(self) -> str:
        return self.title

    @property
    def is_published(self) -> bool:
        return self.status == NewsStatus.PUBLISHED

    def unpublish(self) -> "NewsPost":
        """公開済みの記事を下書きへ戻す。公開日時は消し、再公開時に付け直す。"""
        if not self.is_published:
            return self
        self.status = NewsStatus.DRAFT
        self.published_at = None
        self.save(update_fields=["status", "published_at"])
        return self

    def publish(self) -> "NewsPost":
        """下書きを公開する（詳細設計書 3.7 の手順2）。公開日時を記録する。

        公開済みの記事に対しては何もしない（公開日時を上書きしない）。
        """
        if self.is_published:
            return self
        self.status = NewsStatus.PUBLISHED
        self.published_at = timezone.now()
        self.save(update_fields=["status", "published_at"])
        return self
