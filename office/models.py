"""優先度4: 事務・その他のモデル（詳細設計書 2.11〜2.13）。

画面（出張費申請・チケット・任意機能）は優先度4の実装工程で追加する。
"""

from django.conf import settings
from django.db import models


class ApprovalStatus(models.TextChoices):
    PENDING = "pending", "申請中"
    APPROVED = "approved", "承認"
    REJECTED = "rejected", "却下"


class TravelExpenseRequest(models.Model):
    """出張費申請（詳細設計書 2.11 TravelExpenseRequest）。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="travel_expense_requests",
        verbose_name="申請者",
    )
    destination = models.CharField("出張先", max_length=100)
    purpose = models.TextField("目的")
    amount = models.DecimalField("金額(円)", max_digits=10, decimal_places=0)
    travel_start = models.DateField("出張開始日")
    travel_end = models.DateField("出張終了日")
    status = models.CharField(
        "ステータス", max_length=10, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_travel_expenses",
        verbose_name="承認者",
    )

    class Meta:
        verbose_name = "出張費申請"
        verbose_name_plural = "出張費申請"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.destination} / {self.user.name}（{self.get_status_display()}）"


class TicketStatus(models.TextChoices):
    OPEN = "open", "未着手"
    IN_PROGRESS = "in_progress", "対応中"
    DONE = "done", "完了"


class TicketPriority(models.TextChoices):
    LOW = "low", "低"
    MEDIUM = "medium", "中"
    HIGH = "high", "高"


class Ticket(models.Model):
    """開発リクエスト（詳細設計書 2.12 Ticket）。"""

    title = models.CharField("タイトル", max_length=150)
    description = models.TextField("説明")
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tickets",
        verbose_name="起票者",
    )
    status = models.CharField(
        "ステータス", max_length=12, choices=TicketStatus.choices, default=TicketStatus.OPEN
    )
    priority = models.CharField(
        "優先度", max_length=10, choices=TicketPriority.choices, default=TicketPriority.MEDIUM
    )
    created_at = models.DateTimeField("作成日時", auto_now_add=True)
    updated_at = models.DateTimeField("更新日時", auto_now=True)

    class Meta:
        verbose_name = "チケット"
        verbose_name_plural = "チケット"
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title


class TicketComment(models.Model):
    """チケットコメント（詳細設計書 2.12 子テーブル）。"""

    ticket = models.ForeignKey(
        Ticket, on_delete=models.CASCADE, related_name="comments", verbose_name="チケット"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ticket_comments",
        verbose_name="投稿者",
    )
    body = models.TextField("本文")
    created_at = models.DateTimeField("作成日時", auto_now_add=True)

    class Meta:
        verbose_name = "チケットコメント"
        verbose_name_plural = "チケットコメント"
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.ticket.title} へのコメント"


class JobHuntingStory(models.Model):
    """就活体験記（詳細設計書 2.13・任意機能）。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="job_hunting_stories",
        verbose_name="投稿者",
    )
    content = models.TextField("内容")
    is_public = models.BooleanField("研究室内に公開", default=False)
    created_at = models.DateTimeField("作成日時", auto_now_add=True)

    class Meta:
        verbose_name = "就活体験記"
        verbose_name_plural = "就活体験記"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user.name} の就活体験記"


class ObVisitStatus(models.TextChoices):
    PENDING = "pending", "調整中"
    CONFIRMED = "confirmed", "確定"
    REJECTED = "rejected", "却下"


class ObVisitRequest(models.Model):
    """OB訪問予約（詳細設計書 2.13・任意機能）。"""

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ob_visit_requests",
        verbose_name="申請者",
    )
    desired_date = models.DateField("希望日")
    status = models.CharField(
        "ステータス", max_length=10, choices=ObVisitStatus.choices, default=ObVisitStatus.PENDING
    )
    notes = models.TextField("備考", blank=True)

    class Meta:
        verbose_name = "OB訪問予約"
        verbose_name_plural = "OB訪問予約"
        ordering = ["desired_date"]

    def __str__(self) -> str:
        return f"{self.requester.name} / {self.desired_date}（{self.get_status_display()}）"
