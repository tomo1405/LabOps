"""入退室履歴から、日ごとの在室時間を組み立てる。"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from .models import AttendanceAction


@dataclass
class DailyStay:
    """1人・1日分の在室記録。

    日をまたぐ滞在は日付境界で分割し、その日に属する時間だけを持つ。
    分割された区間かどうかは continued_from_previous / continues_to_next で表す。
    """

    day: date
    user: object
    intervals: list = field(default_factory=list)  # [開始日時 or None, 終了日時 or None]
    continued_from_previous: bool = False  # 前日からの滞在が続いている
    continues_to_next: bool = False  # 翌日へ滞在が続く

    @property
    def first_enter(self) -> datetime | None:
        return self.intervals[0][0] if self.intervals else None

    @property
    def last_exit(self) -> datetime | None:
        return self.intervals[-1][1] if self.intervals else None

    @property
    def is_open(self) -> bool:
        """対応する退室が記録されていない区間が残っているか（打刻漏れ・在室中）。

        日をまたいだだけの区間は continues_to_next で表すため、ここには含めない。
        """
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


def _start_of_next_day(moment: datetime) -> datetime:
    """その日時が属する日の翌日0時（ローカル）。"""
    return timezone.make_aware(datetime.combine(moment.date() + timedelta(days=1), time.min))


class _StayBuilder:
    """日付×人の在室記録を組み立てる作業用のまとめ役。"""

    def __init__(self) -> None:
        self._stays: dict[tuple[date, int], DailyStay] = {}

    def _stay(self, day: date, user) -> DailyStay:
        return self._stays.setdefault((day, user.pk), DailyStay(day=day, user=user))

    def add_span(self, user, enter_at: datetime, exit_at: datetime) -> None:
        """対になった区間を、日付境界で分割して各日に配分する。"""
        cursor = enter_at
        while True:
            boundary = _start_of_next_day(cursor)
            stay = self._stay(cursor.date(), user)
            if exit_at <= boundary:
                # ちょうど0時の退室はこの日で閉じ、翌日の行は作らない
                stay.intervals.append([cursor, exit_at])
                return
            stay.intervals.append([cursor, boundary])
            stay.continues_to_next = True
            cursor = boundary
            self._stay(cursor.date(), user).continued_from_previous = True

    def add_open(self, user, enter_at: datetime) -> None:
        """対応する退室がない入室。区間を閉じずに残す（在室中・打刻漏れ）。"""
        self._stay(enter_at.date(), user).intervals.append([enter_at, None])

    def add_orphan_exit(self, user, exit_at: datetime) -> None:
        """入室の記録がない退室。区間の開始が不明なので単独で残す。"""
        self._stay(exit_at.date(), user).intervals.append([None, exit_at])

    def result(self) -> list[DailyStay]:
        for stay in self._stays.values():
            stay.intervals.sort(key=lambda span: span[0] or span[1])
        return sorted(self._stays.values(), key=lambda s: (s.day, s.user.name), reverse=True)


def build_daily_stays(logs) -> list[DailyStay]:
    """履歴（新しい順でも古い順でもよい）を、日付×人の在室記録にまとめる。

    まず人ごとの時系列で入室と退室を対応付け、その区間を日付境界で分割して
    各日へ配分する。日をまたぐ滞在も、両日にその日の分だけ集計される。

    対にならない記録（退室だけ、入室が連続）は打刻漏れとして扱い、区間を閉じずに残す。
    """
    by_user: dict[int, list] = {}
    for log in sorted(logs, key=lambda x: (x.recorded_at, x.pk)):
        by_user.setdefault(log.user_id, []).append(log)

    builder = _StayBuilder()
    for user_logs in by_user.values():
        user = user_logs[0].user
        open_enter: datetime | None = None
        for log in user_logs:
            local = timezone.localtime(log.recorded_at)
            if log.action == AttendanceAction.ENTER:
                if open_enter is not None:
                    # 退室のない入室が続いた。前の区間は閉じずに残す
                    builder.add_open(user, open_enter)
                open_enter = local
            elif open_enter is None:
                builder.add_orphan_exit(user, local)
            else:
                builder.add_span(user, open_enter, local)
                open_enter = None
        if open_enter is not None:
            builder.add_open(user, open_enter)

    return builder.result()
