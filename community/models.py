"""優先度2: 情報共有・コミュニケーション系のモデル（詳細設計書 2.2 / 2.9 / 2.10）。"""

import secrets

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

    def toggle(self, source: str = "web", tag=None) -> "AttendanceStatus":
        """在室／不在を反転して保存し、履歴を1件残す（詳細設計書 4章 /attendance/toggle）。

        実処理は community.attendance に集約している。状態の更新と履歴の記録を
        1トランザクションで行い、対象メンバーの行をロックして同時打刻を直列化する。
        """
        from .attendance import toggle_attendance

        refreshed = toggle_attendance(self.user, source=source, tag=tag)
        self.status = refreshed.status
        return self

    def set_state(self, entering: bool, source: str = "web", tag=None) -> "AttendanceStatus":
        """在室／不在を明示的に設定し、履歴を1件残す。

        NFCタグからの打刻のように「入室」「退室」を直接指定する場合に使う。
        """
        from .attendance import set_attendance

        refreshed = set_attendance(self.user, entering, source=source, tag=tag)
        self.status = refreshed.status
        return self


class AttendanceAction(models.TextChoices):
    ENTER = "enter", "入室"
    EXIT = "exit", "退室"


class AttendanceSource(models.TextChoices):
    WEB = "web", "画面から"
    NFC = "nfc", "NFCタグ"


def generate_nfc_token() -> str:
    """NFCタグに書き込むURLの識別子。推測できない値にする。"""
    return secrets.token_urlsafe(16)


class NfcTag(models.Model):
    """入退室登録に使うNFCタグ。メンバー1人につき1枚以上を発行する。

    タグにはこのレコードのURLを書き込む。URLを開くとログインなしでそのメンバーの
    在室／不在が反転するため、**URLそのものが打刻用の鍵**になる。
    紛失・流出したタグは、管理画面から無効化するかトークンを再発行する。
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="nfc_tags",
        verbose_name="対象メンバー",
        help_text="このタグを読んだときに入退室が切り替わるメンバー",
    )
    label = models.CharField("名称", max_length=50, blank=True, help_text="例: 入り口に貼るタグ（予備）")
    location = models.CharField("設置場所", max_length=100, blank=True)
    token = models.CharField(
        "トークン", max_length=64, unique=True, default=generate_nfc_token, editable=False
    )
    is_active = models.BooleanField("有効", default=True)
    created_at = models.DateTimeField("作成日時", auto_now_add=True)

    class Meta:
        verbose_name = "NFCタグ"
        verbose_name_plural = "NFCタグ"
        ordering = ["user__name", "label"]

    def __str__(self) -> str:
        return f"{self.user.name}{f'（{self.label}）' if self.label else ''}"

    @property
    def url_path(self) -> str:
        """タグに書き込むURL（ホスト名は運用環境に応じて前置する）。"""
        from django.urls import reverse

        return reverse("community:attendance_nfc", args=[self.token])

    def regenerate_token(self) -> str:
        """トークンを作り直す。紛失したタグを無効にするときに使う。"""
        self.token = generate_nfc_token()
        self.save(update_fields=["token"])
        return self.token


class AttendanceLog(models.Model):
    """入退室の履歴。在室状況を切り替えるたびに1件記録する。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="attendance_logs",
        verbose_name="ユーザー",
    )
    action = models.CharField("種別", max_length=10, choices=AttendanceAction.choices)
    source = models.CharField(
        "登録元", max_length=10, choices=AttendanceSource.choices, default=AttendanceSource.WEB
    )
    tag = models.ForeignKey(
        NfcTag,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
        verbose_name="NFCタグ",
    )
    recorded_at = models.DateTimeField("記録日時", auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "入退室履歴"
        verbose_name_plural = "入退室履歴"
        ordering = ["-recorded_at", "-id"]
        indexes = [models.Index(fields=["user", "-recorded_at"])]

    def __str__(self) -> str:
        return f"{self.recorded_at:%Y-%m-%d %H:%M} {self.user.name} {self.get_action_display()}"

    @property
    def is_enter(self) -> bool:
        return self.action == AttendanceAction.ENTER


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
