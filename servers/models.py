"""優先度3: サーバー利用状況・申請系のモデル（詳細設計書 2.6〜2.8）。

ダッシュボード・申請画面・データ収集バッチは優先度3の実装工程で追加する。
"""

from django.conf import settings
from django.db import models


class ServerCategory(models.TextChoices):
    LAB = "lab", "研究室サーバー"
    DEPT = "dept", "学科サーバー"


class Server(models.Model):
    """サーバーマスタ（詳細設計書 2.6 Server）。"""

    name = models.CharField("名称", max_length=50)
    category = models.CharField("種別", max_length=10, choices=ServerCategory.choices)
    location = models.CharField("設置場所", max_length=100, blank=True)

    class Meta:
        verbose_name = "サーバー"
        verbose_name_plural = "サーバー"
        ordering = ["category", "name"]

    def __str__(self) -> str:
        return f"{self.name}（{self.get_category_display()}）"


class ServerUsageSnapshot(models.Model):
    """サーバー利用状況スナップショット（詳細設計書 2.7 ServerUsageSnapshot）。"""

    server = models.ForeignKey(
        Server, on_delete=models.CASCADE, related_name="usage_snapshots", verbose_name="サーバー"
    )
    captured_at = models.DateTimeField("取得日時", db_index=True)
    cpu_percent = models.FloatField("CPU使用率(%)")
    memory_percent = models.FloatField("メモリ使用率(%)")
    disk_percent = models.FloatField("ディスク使用率(%)")
    gpu_percent = models.FloatField("GPU使用率(%)", null=True, blank=True)

    class Meta:
        verbose_name = "サーバー利用状況"
        verbose_name_plural = "サーバー利用状況"
        ordering = ["-captured_at"]
        indexes = [models.Index(fields=["server", "-captured_at"])]

    def __str__(self) -> str:
        return f"{self.server.name} {self.captured_at:%Y-%m-%d %H:%M}"


class RequestStatus(models.TextChoices):
    PENDING = "pending", "申請中"
    APPROVED = "approved", "承認"
    REJECTED = "rejected", "却下"


class ServerLongTermRequest(models.Model):
    """サーバー長期利用申請（詳細設計書 2.8 ServerLongTermRequest）。"""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="server_requests",
        verbose_name="申請者",
    )
    server = models.ForeignKey(
        Server, on_delete=models.CASCADE, related_name="long_term_requests", verbose_name="サーバー"
    )
    start_date = models.DateField("利用開始日")
    end_date = models.DateField("利用終了日")
    reason = models.TextField("利用理由")
    status = models.CharField(
        "ステータス", max_length=10, choices=RequestStatus.choices, default=RequestStatus.PENDING
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_requests",
        verbose_name="承認者",
    )
    reviewed_at = models.DateTimeField("承認日時", null=True, blank=True)

    class Meta:
        verbose_name = "サーバー長期利用申請"
        verbose_name_plural = "サーバー長期利用申請"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.server.name} / {self.user.name}（{self.get_status_display()}）"
