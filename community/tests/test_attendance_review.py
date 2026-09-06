"""在室メンバー可視化機能のテスト（コードレビュー REV-ATT-001〜003 に対応）。"""

from datetime import datetime, time, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.db.models import QuerySet
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from community import attendance as attendance_service
from community.attendance_summary import build_daily_stays
from community.models import (
    AttendanceAction,
    AttendanceLog,
    AttendanceSource,
    AttendanceState,
    AttendanceStatus,
    NfcTag,
)
from community.views import MAX_HISTORY_DATE, MIN_HISTORY_DATE

User = get_user_model()


def log_at(user, action, when, source=AttendanceSource.WEB, tag=None) -> AttendanceLog:
    """recorded_at は auto_now_add のため、作成後に書き換える。"""
    log = AttendanceLog.objects.create(user=user, action=action, source=source, tag=tag)
    AttendanceLog.objects.filter(pk=log.pk).update(recorded_at=when)
    log.refresh_from_db()
    return log


class AttendanceConcurrencyTests(TestCase):
    """REV-ATT-001: 状態更新と履歴作成を原子的・排他的に行う。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")
        cls.tag = NfcTag.objects.create(user=cls.user, label="入り口用")

    def setUp(self):
        self.client.force_login(self.user)

    def _last_log(self) -> AttendanceLog | None:
        return AttendanceLog.objects.order_by("-recorded_at", "-id").first()

    def _assert_status_matches_last_log(self):
        status = AttendanceStatus.objects.get(user=self.user)
        last = self._last_log()
        self.assertIsNotNone(last)
        self.assertEqual(status.is_present, last.is_enter)

    def test_status_row_is_locked_before_the_state_is_read(self):
        """在室状況の行をロックしてから判定していること。"""
        original = QuerySet.select_for_update
        with mock.patch.object(QuerySet, "select_for_update", autospec=True, side_effect=original) as locked:
            attendance_service.toggle_attendance(self.user)
        self.assertTrue(locked.called)

    def test_toggle_runs_inside_a_transaction(self):
        seen = {}

        def record(*args, **kwargs):
            from django.db import transaction

            seen["in_atomic_block"] = transaction.get_connection().in_atomic_block
            return mock.DEFAULT

        with mock.patch.object(
            AttendanceLog.objects, "create", side_effect=record, wraps=AttendanceLog.objects.create
        ):
            attendance_service.toggle_attendance(self.user)
        self.assertTrue(seen["in_atomic_block"])

    def test_log_failure_rolls_back_the_status_change(self):
        """履歴の作成に失敗したら、状態の更新も残らない。"""
        AttendanceStatus.objects.create(user=self.user)
        with (
            mock.patch.object(AttendanceLog.objects, "create", side_effect=DatabaseError("boom")),
            self.assertRaises(DatabaseError),
        ):
            attendance_service.toggle_attendance(self.user)
        self.assertEqual(AttendanceStatus.objects.get(user=self.user).status, AttendanceState.ABSENT)
        self.assertFalse(AttendanceLog.objects.exists())

    def test_nfc_cooldown_is_evaluated_after_taking_the_lock(self):
        """クールダウン判定がロック取得後に行われること。"""
        order = []
        original_lock = attendance_service._lock_status
        original_check = attendance_service._has_recent_nfc_log

        def lock(user):
            order.append("lock")
            return original_lock(user)

        def check(user):
            order.append("cooldown")
            return original_check(user)

        with (
            mock.patch.object(attendance_service, "_lock_status", side_effect=lock),
            mock.patch.object(attendance_service, "_has_recent_nfc_log", side_effect=check),
        ):
            attendance_service.toggle_attendance_by_tag(self.tag)
        self.assertEqual(order, ["lock", "cooldown"])

    def test_second_nfc_read_within_cooldown_records_no_extra_log(self):
        """同じタグを続けて読んでも履歴は1件だけになる。"""
        url = reverse("community:attendance_nfc", args=[self.tag.token])
        self.client.get(url)
        self.client.get(url)
        self.assertEqual(AttendanceLog.objects.count(), 1)
        self._assert_status_matches_last_log()

    def test_repeated_web_toggles_keep_status_and_log_consistent(self):
        for _ in range(4):
            self.client.post(reverse("community:attendance_toggle"))
        self.assertEqual(AttendanceLog.objects.count(), 4)
        self._assert_status_matches_last_log()

    def test_web_and_nfc_operations_keep_status_and_log_consistent(self):
        self.client.post(reverse("community:attendance_toggle"))
        # クールダウンを避けるため、直前のNFC履歴が無い状態で読ませる
        self.client.get(reverse("community:attendance_nfc", args=[self.tag.token]))
        self.client.post(reverse("community:attendance_toggle"))
        self.assertEqual(AttendanceLog.objects.count(), 3)
        self._assert_status_matches_last_log()

    def test_status_is_created_when_missing(self):
        self.assertFalse(AttendanceStatus.objects.filter(user=self.user).exists())
        attendance_service.toggle_attendance(self.user)
        self.assertTrue(AttendanceStatus.objects.get(user=self.user).is_present)


class AttendanceHistoryDateBoundaryTests(TestCase):
    """REV-ATT-002: 有効な最大・最小日付でも500にしない。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("community:attendance_history")

    def test_maximum_iso_date_does_not_error(self):
        response = self.client.get(self.url, {"from": "9999-12-31", "to": "9999-12-31"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["date_to"], MAX_HISTORY_DATE)

    def test_minimum_iso_date_does_not_error(self):
        response = self.client.get(self.url, {"from": "0001-01-01", "to": "0001-01-01"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["date_from"], MIN_HISTORY_DATE)

    def test_only_one_side_at_the_boundary(self):
        response = self.client.get(self.url, {"to": "9999-12-31"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["date_to"], MAX_HISTORY_DATE)

    def test_reversed_range_is_swapped(self):
        response = self.client.get(self.url, {"from": "9999-12-31", "to": "0001-01-01"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["date_from"], MIN_HISTORY_DATE)
        self.assertEqual(response.context["date_to"], MAX_HISTORY_DATE)

    def test_full_range_still_returns_records(self):
        log_at(self.user, AttendanceAction.ENTER, timezone.now())
        response = self.client.get(self.url, {"from": "0001-01-01", "to": "9999-12-31"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["logs"]), 1)

    def test_malformed_date_falls_back_to_the_default(self):
        response = self.client.get(self.url, {"from": "not-a-date"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["date_to"], timezone.localdate())


class OvernightStayTests(TestCase):
    """REV-ATT-003: 日をまたぐ滞在を日ごとに配分する。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")

    def _at(self, day_offset: int, hour: int, minute: int = 0):
        day = timezone.localdate() + timedelta(days=day_offset)
        return timezone.make_aware(datetime.combine(day, time(hour=hour, minute=minute)))

    def _stays_by_day(self, logs):
        return {stay.day: stay for stay in build_daily_stays(logs)}

    def test_overnight_stay_is_split_across_both_days(self):
        logs = [
            log_at(self.user, AttendanceAction.ENTER, self._at(-1, 23)),
            log_at(self.user, AttendanceAction.EXIT, self._at(0, 1)),
        ]
        stays = self._stays_by_day(logs)
        yesterday = timezone.localdate() - timedelta(days=1)
        self.assertEqual(stays[yesterday].total, timedelta(hours=1))
        self.assertEqual(stays[timezone.localdate()].total, timedelta(hours=1))

    def test_previous_day_is_not_marked_as_present(self):
        logs = [
            log_at(self.user, AttendanceAction.ENTER, self._at(-1, 23)),
            log_at(self.user, AttendanceAction.EXIT, self._at(0, 1)),
        ]
        stays = self._stays_by_day(logs)
        yesterday = stays[timezone.localdate() - timedelta(days=1)]
        self.assertFalse(yesterday.is_open)
        self.assertTrue(yesterday.continues_to_next)
        self.assertTrue(stays[timezone.localdate()].continued_from_previous)

    def test_stay_spanning_several_days_fills_the_middle_day(self):
        logs = [
            log_at(self.user, AttendanceAction.ENTER, self._at(-2, 22)),
            log_at(self.user, AttendanceAction.EXIT, self._at(0, 2)),
        ]
        stays = self._stays_by_day(logs)
        middle = stays[timezone.localdate() - timedelta(days=1)]
        self.assertEqual(middle.total, timedelta(hours=24))
        self.assertTrue(middle.continued_from_previous)
        self.assertTrue(middle.continues_to_next)

    def test_exit_exactly_at_midnight_closes_the_previous_day_only(self):
        logs = [
            log_at(self.user, AttendanceAction.ENTER, self._at(-1, 23)),
            log_at(self.user, AttendanceAction.EXIT, self._at(0, 0)),
        ]
        stays = self._stays_by_day(logs)
        self.assertNotIn(timezone.localdate(), stays)
        yesterday = stays[timezone.localdate() - timedelta(days=1)]
        self.assertEqual(yesterday.total, timedelta(hours=1))
        self.assertFalse(yesterday.continues_to_next)

    def test_still_present_is_shown_only_on_the_unpaired_interval(self):
        logs = [log_at(self.user, AttendanceAction.ENTER, self._at(-1, 23))]
        stays = self._stays_by_day(logs)
        self.assertTrue(stays[timezone.localdate() - timedelta(days=1)].is_open)
        self.assertNotIn(timezone.localdate(), stays)

    def test_enter_before_the_range_keeps_the_exit_as_an_orphan(self):
        """表示期間の開始前に入室した場合、期間内の退室は開始不明として残す。"""
        logs = [log_at(self.user, AttendanceAction.EXIT, self._at(0, 9))]
        stay = build_daily_stays(logs)[0]
        self.assertIsNone(stay.first_enter)
        self.assertEqual(stay.total, timedelta())
        self.assertFalse(stay.is_open)

    def test_enter_inside_the_range_without_exit_stays_open(self):
        """期間内に入室し、期間の後で退室した場合は在室中として残す。"""
        logs = [log_at(self.user, AttendanceAction.ENTER, self._at(0, 9))]
        stay = build_daily_stays(logs)[0]
        self.assertTrue(stay.is_open)
        self.assertEqual(stay.total, timedelta())

    def test_same_day_stays_are_unaffected(self):
        logs = [
            log_at(self.user, AttendanceAction.ENTER, self._at(0, 9)),
            log_at(self.user, AttendanceAction.EXIT, self._at(0, 12)),
            log_at(self.user, AttendanceAction.ENTER, self._at(0, 13)),
            log_at(self.user, AttendanceAction.EXIT, self._at(0, 18)),
        ]
        stay = build_daily_stays(logs)[0]
        self.assertEqual(stay.total, timedelta(hours=8))
        self.assertFalse(stay.continued_from_previous)
        self.assertFalse(stay.continues_to_next)

    def test_history_page_labels_a_continued_day(self):
        self.client.force_login(self.user)
        log_at(self.user, AttendanceAction.ENTER, self._at(-1, 23))
        log_at(self.user, AttendanceAction.EXIT, self._at(0, 1))
        response = self.client.get(reverse("community:attendance_history"))
        self.assertContains(response, "前日から")
        self.assertContains(response, "翌日へ")
        self.assertNotContains(response, "在室中")
