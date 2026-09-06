"""在室状態の更新をまとめて行うサービス。

在室状況の読み取り・NFCのクールダウン判定・状態の更新・履歴の記録を
1つのトランザクションで実行し、対象メンバーの行をロックして同時打刻を直列化する。

画面からの切替とNFC打刻が同時に届いても、
「切り替えるたびに履歴を1件記録する」という前提が崩れないようにするための入口。
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    AttendanceAction,
    AttendanceLog,
    AttendanceSource,
    AttendanceState,
    AttendanceStatus,
)

# 同じメンバーを続けて読んだときに二重打刻しない時間（秒）
NFC_COOLDOWN_SECONDS = 30


def _lock_status(user) -> AttendanceStatus:
    """在室状況を行ロック付きで取得する。無ければ作成する。

    レコードの新規作成が同時に起きると一意制約違反になるため、
    その場合は先に作られたレコードを読み直してロックを取る。
    """
    status = AttendanceStatus.objects.select_for_update().filter(user=user).first()
    if status is not None:
        return status
    try:
        # 失敗しても外側のトランザクションを壊さないよう savepoint で包む
        with transaction.atomic():
            AttendanceStatus.objects.create(user=user)
    except IntegrityError:
        pass
    return AttendanceStatus.objects.select_for_update().get(user=user)


def _has_recent_nfc_log(user) -> bool:
    """クールダウン中に同じメンバーのNFC打刻が既にあるか。

    ロックを取った後に呼ぶこと。先に打刻したリクエストの履歴を必ず見えるようにする。
    """
    return AttendanceLog.objects.filter(
        user=user,
        source=AttendanceSource.NFC,
        recorded_at__gte=timezone.now() - timedelta(seconds=NFC_COOLDOWN_SECONDS),
    ).exists()


def _apply(status: AttendanceStatus, *, entering: bool, source: str, tag=None) -> AttendanceStatus:
    """状態を更新し、対応する履歴を1件残す。"""
    status.status = AttendanceState.PRESENT if entering else AttendanceState.ABSENT
    status.save(update_fields=["status", "updated_at"])
    AttendanceLog.objects.create(
        user=status.user,
        action=AttendanceAction.ENTER if entering else AttendanceAction.EXIT,
        source=source,
        tag=tag,
    )
    return status


@transaction.atomic
def toggle_attendance(user, source: str = AttendanceSource.WEB, tag=None) -> AttendanceStatus:
    """在室／不在を反転して保存し、履歴を1件残す。"""
    status = _lock_status(user)
    return _apply(status, entering=not status.is_present, source=source, tag=tag)


@transaction.atomic
def set_attendance(user, entering: bool, source: str = AttendanceSource.WEB, tag=None) -> AttendanceStatus:
    """在室／不在を明示的に設定し、履歴を1件残す。"""
    return _apply(_lock_status(user), entering=entering, source=source, tag=tag)


@transaction.atomic
def toggle_attendance_by_tag(tag) -> tuple[AttendanceStatus, bool]:
    """NFCタグからの打刻。切り替えたかどうかを合わせて返す。

    クールダウンの判定はロックを取ってから行うため、
    同じタグがほぼ同時に読まれても履歴は1件だけになる。
    """
    status = _lock_status(tag.user)
    if _has_recent_nfc_log(tag.user):
        return status, False
    status = _apply(status, entering=not status.is_present, source=AttendanceSource.NFC, tag=tag)
    return status, True
