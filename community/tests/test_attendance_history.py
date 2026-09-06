"""入退室履歴とNFCタグからの打刻のテスト。"""

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from community.attendance_summary import build_daily_stays
from community.models import (
    AttendanceAction,
    AttendanceLog,
    AttendanceSource,
    AttendanceState,
    AttendanceStatus,
    NfcTag,
)

User = get_user_model()


def log_at(user, action, when, source=AttendanceSource.WEB, tag=None) -> AttendanceLog:
    """recorded_at は auto_now_add のため、作成後に書き換える。"""
    log = AttendanceLog.objects.create(user=user, action=action, source=source, tag=tag)
    AttendanceLog.objects.filter(pk=log.pk).update(recorded_at=when)
    log.refresh_from_db()
    return log


class AttendanceLogRecordingTests(TestCase):
    """在室状態を切り替えるたびに履歴が残る。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")

    def setUp(self):
        self.client.force_login(self.user)

    def test_toggle_records_enter_then_exit(self):
        self.client.post(reverse("community:attendance_toggle"))
        self.client.post(reverse("community:attendance_toggle"))
        actions = list(AttendanceLog.objects.order_by("id").values_list("action", "source"))
        self.assertEqual(
            actions,
            [(AttendanceAction.ENTER, AttendanceSource.WEB), (AttendanceAction.EXIT, AttendanceSource.WEB)],
        )

    def test_status_and_log_stay_consistent(self):
        self.client.post(reverse("community:attendance_toggle"))
        status = AttendanceStatus.objects.get(user=self.user)
        self.assertEqual(status.status, AttendanceState.PRESENT)
        self.assertTrue(AttendanceLog.objects.get().is_enter)


class AttendanceHistoryViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")
        cls.mate = User.objects.create_user(email="mate@example.com", password="pw12345!", name="同僚")

    def setUp(self):
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        self.old_day = self.today - timedelta(days=30)

        def aware(day, hour):
            return timezone.make_aware(datetime.combine(day, time(hour=hour)))

        log_at(self.user, AttendanceAction.ENTER, aware(self.today, 9))
        log_at(self.user, AttendanceAction.EXIT, aware(self.today, 18))
        log_at(self.mate, AttendanceAction.ENTER, aware(self.today, 13))
        log_at(self.user, AttendanceAction.ENTER, aware(self.old_day, 10))

    def test_requires_login(self):
        self.client.logout()
        url = reverse("community:attendance_history")
        self.assertRedirects(self.client.get(url), f"{reverse('accounts:login')}?next={url}")

    def test_shows_all_members_by_default(self):
        response = self.client.get(reverse("community:attendance_history"))
        self.assertEqual(response.status_code, 200)
        names = {log.user.name for log in response.context["logs"]}
        self.assertEqual(names, {"本人", "同僚"})

    def test_default_range_excludes_old_records(self):
        """既定は直近7日。30日前の記録は出さない。"""
        response = self.client.get(reverse("community:attendance_history"))
        self.assertEqual(len(response.context["logs"]), 3)

    def test_filter_by_member(self):
        response = self.client.get(reverse("community:attendance_history"), {"member": self.mate.pk})
        self.assertEqual({log.user for log in response.context["logs"]}, {self.mate})

    def test_filter_by_period_includes_old_records(self):
        response = self.client.get(
            reverse("community:attendance_history"),
            {"from": self.old_day.isoformat(), "to": self.today.isoformat()},
        )
        self.assertEqual(len(response.context["logs"]), 4)

    def test_invalid_date_falls_back_to_default(self):
        """履歴画面は日付が不正でも404にせず、既定の期間で表示する。"""
        response = self.client.get(reverse("community:attendance_history"), {"from": "2026-13-45"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["date_from"], self.today - timedelta(days=6))

    def test_reversed_period_is_corrected(self):
        response = self.client.get(
            reverse("community:attendance_history"),
            {"from": self.today.isoformat(), "to": self.old_day.isoformat()},
        )
        self.assertEqual(response.context["date_from"], self.old_day)
        self.assertEqual(response.context["date_to"], self.today)

    def test_daily_stay_totals_working_hours(self):
        response = self.client.get(reverse("community:attendance_history"))
        stay = next(s for s in response.context["stays"] if s.user == self.user)
        self.assertEqual(stay.total, timedelta(hours=9))
        self.assertEqual(stay.total_label, "9時間00分")

    def test_open_stay_is_marked_as_present(self):
        response = self.client.get(reverse("community:attendance_history"))
        stay = next(s for s in response.context["stays"] if s.user == self.mate)
        self.assertTrue(stay.is_open)
        self.assertEqual(stay.total, timedelta())


class DailyStayTests(TestCase):
    """在室時間の集計（打刻漏れの扱い）。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")

    def _aware(self, hour):
        return timezone.make_aware(datetime.combine(timezone.localdate(), time(hour=hour)))

    def test_multiple_intervals_are_summed(self):
        logs = [
            log_at(self.user, AttendanceAction.ENTER, self._aware(9)),
            log_at(self.user, AttendanceAction.EXIT, self._aware(12)),
            log_at(self.user, AttendanceAction.ENTER, self._aware(13)),
            log_at(self.user, AttendanceAction.EXIT, self._aware(18)),
        ]
        stay = build_daily_stays(logs)[0]
        self.assertEqual(stay.total, timedelta(hours=8))

    def test_exit_without_enter_is_excluded_from_total(self):
        logs = [log_at(self.user, AttendanceAction.EXIT, self._aware(18))]
        stay = build_daily_stays(logs)[0]
        self.assertEqual(stay.total, timedelta())
        self.assertIsNone(stay.first_enter)

    def test_consecutive_enters_do_not_close_the_interval(self):
        logs = [
            log_at(self.user, AttendanceAction.ENTER, self._aware(9)),
            log_at(self.user, AttendanceAction.ENTER, self._aware(10)),
        ]
        stay = build_daily_stays(logs)[0]
        self.assertTrue(stay.is_open)
        self.assertEqual(stay.total, timedelta())


class AttendanceNfcTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")
        cls.tag = NfcTag.objects.create(label="入り口", location="研究室ドア横")

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("community:attendance_nfc", args=[self.tag.token])

    def test_get_shows_confirmation_without_changing_state(self):
        """タグを読んだだけでは打刻しない（先読みでの誤打刻を避ける）。"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "入り口")
        self.assertFalse(AttendanceLog.objects.exists())

    def test_post_enter_records_with_nfc_source(self):
        response = self.client.post(self.url, {"action": "enter"})
        self.assertRedirects(response, reverse("community:attendance_list"))
        log = AttendanceLog.objects.get()
        self.assertEqual(log.action, AttendanceAction.ENTER)
        self.assertEqual(log.source, AttendanceSource.NFC)
        self.assertEqual(log.tag, self.tag)
        self.assertTrue(AttendanceStatus.objects.get(user=self.user).is_present)

    def test_post_exit_records_exit(self):
        self.client.post(self.url, {"action": "enter"})
        self.client.post(self.url, {"action": "exit"})
        self.assertFalse(AttendanceStatus.objects.get(user=self.user).is_present)
        self.assertEqual(AttendanceLog.objects.count(), 2)

    def test_unknown_token_returns_404(self):
        response = self.client.get(reverse("community:attendance_nfc", args=["unknown-token"]))
        self.assertEqual(response.status_code, 404)

    def test_inactive_tag_returns_404(self):
        self.tag.is_active = False
        self.tag.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_requires_login(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={self.url}")

    def test_tokens_are_unique_per_tag(self):
        other = NfcTag.objects.create(label="別の入り口")
        self.assertNotEqual(self.tag.token, other.token)

    def test_url_path_points_to_the_tag(self):
        self.assertEqual(self.tag.url_path, self.url)
