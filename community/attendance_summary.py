"""入退室履歴から、日ごとの在室時間を組み立てる。"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from django.utils import timezone

from .models import AttendanceAction


@dataclass
class DailyStay:
    """1人・1日分の在室記録。"""

    day: date
    user: object
    intervals: list = field(default_factory=list)  # (入室日時, 退室日時 or None)

    @property
    def first_enter(self) -> datetime | None:
        return self.intervals[0][0] if self.intervals else None

    @property
    def last_exit(self) -> datetime | None:
        return self.intervals[-1][1] if self.intervals else None

    @property
    def is_open(self) -> bool:
        """退室が記録されていない区間が残っているか（在室したまま日をまたいだ等）。"""
        return bool(self.intervals) and self.intervals[-1][1] is None

    @property
    def total(self) -> timedelta:
        """在室時間の合計。退室のない区間は集計から除く。"""
        return sum(
            (exit_at - enter_at for enter_at, exit_at in self.intervals if enter_at and exit_at),
            timedelta(),
        )

    @property
    def total_label(self) -> str:
        minutes = int(self.total.total_seconds() // 60)
        return f"{minutes // 60}時間{minutes % 60:02d}分"


def build_daily_stays(logs) -> list[DailyStay]:
    """履歴（新しい順でも古い順でもよい）を、日付×人の在室記録にまとめる。

    入室→退室の順で対になる区間を作る。対にならない記録（退室だけ、入室が連続）は
    打刻漏れとして扱い、区間を閉じずに残す。
    """
    stays: dict[tuple[date, int], DailyStay] = {}
    for log in sorted(logs, key=lambda x: x.recorded_at):
        local = timezone.localtime(log.recorded_at)
        key = (local.date(), log.user_id)
        stay = stays.setdefault(key, DailyStay(day=local.date(), user=log.user))
        if log.action == AttendanceAction.ENTER:
            stay.intervals.append([local, None])
        elif stay.intervals and stay.intervals[-1][1] is None:
            stay.intervals[-1][1] = local
        else:
            # 入室の記録がない退室。区間の開始が不明なので、単独の記録として残す
            stay.intervals.append([None, local])

    return sorted(stays.values(), key=lambda s: (s.day, s.user.name), reverse=True)
