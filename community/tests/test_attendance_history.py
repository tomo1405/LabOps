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
    """メンバーごとのNFCタグ。URLを開くと、ログインなしで在室／不在が反転する。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")
        cls.other = User.objects.create_user(email="other@example.com", password="pw12345!", name="他人")
        cls.tag = NfcTag.objects.create(user=cls.user, label="入り口用", location="研究室ドア横")

    def setUp(self):
        self.url = reverse("community:attendance_nfc", args=[self.tag.token])

    def _age_last_log(self, seconds: int = 120) -> None:
        """直前の打刻を過去にずらし、連続読み取り扱いを解除する。"""
        log = AttendanceLog.objects.order_by("-id").first()
        AttendanceLog.objects.filter(pk=log.pk).update(
            recorded_at=timezone.now() - timedelta(seconds=seconds)
        )

    def test_opening_url_marks_the_member_present(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AttendanceStatus.objects.get(user=self.user).is_present)

    def test_opening_url_again_marks_the_member_absent(self):
        """もう一度読むと反転して退室になる。"""
        self.client.get(self.url)
        self._age_last_log()
        self.client.get(self.url)
        self.assertFalse(AttendanceStatus.objects.get(user=self.user).is_present)

    def test_works_without_login(self):
        """ログインしていなくても打刻できる（ログイン画面へ飛ばさない）。"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(reverse("accounts:login"), response.get("Location", ""))

    def test_records_log_with_nfc_source_and_tag(self):
        self.client.get(self.url)
        log = AttendanceLog.objects.get()
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.action, AttendanceAction.ENTER)
        self.assertEqual(log.source, AttendanceSource.NFC)
        self.assertEqual(log.tag, self.tag)

    def test_tag_only_affects_its_own_member(self):
        """他メンバーの在室状態は変わらない。"""
        AttendanceStatus.objects.create(user=self.other, status=AttendanceState.ABSENT)
        self.client.get(self.url)
        self.assertFalse(AttendanceStatus.objects.get(user=self.other).is_present)

    def test_consecutive_reads_do_not_toggle_twice(self):
        """かざし直しや先読みで、入室直後に退室扱いにならない。"""
        self.client.get(self.url)
        response = self.client.get(self.url)
        self.assertTrue(AttendanceStatus.objects.get(user=self.user).is_present)
        self.assertEqual(AttendanceLog.objects.count(), 1)
        self.assertFalse(response.context["toggled"])

    def test_toggle_resumes_after_cooldown(self):
        self.client.get(self.url)
        self._age_last_log()
        response = self.client.get(self.url)
        self.assertTrue(response.context["toggled"])
        self.assertEqual(AttendanceLog.objects.count(), 2)

    def test_result_page_shows_member_and_state(self):
        response = self.client.get(self.url)
        self.assertContains(response, "本人")
        self.assertContains(response, "在室")

    def test_response_is_not_cached(self):
        response = self.client.get(self.url)
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_unknown_token_returns_404(self):
        response = self.client.get(reverse("community:attendance_nfc", args=["unknown-token"]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(AttendanceLog.objects.exists())

    def test_inactive_tag_returns_404(self):
        self.tag.is_active = False
        self.tag.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertFalse(AttendanceLog.objects.exists())

    def test_regenerated_token_invalidates_the_old_url(self):
        """紛失したタグは、トークン再発行で使えなくなる。"""
        old_url = self.url
        self.tag.regenerate_token()
        self.assertEqual(self.client.get(old_url).status_code, 404)
        new_url = reverse("community:attendance_nfc", args=[self.tag.token])
        self.assertEqual(self.client.get(new_url).status_code, 200)

    def test_post_is_rejected(self):
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 405)

    def test_tokens_are_unique_per_tag(self):
        other_tag = NfcTag.objects.create(user=self.other)
        self.assertNotEqual(self.tag.token, other_tag.token)

    def test_member_can_have_multiple_tags(self):
        spare = NfcTag.objects.create(user=self.user, label="予備")
        self.client.get(reverse("community:attendance_nfc", args=[spare.token]))
        self.assertTrue(AttendanceStatus.objects.get(user=self.user).is_present)

    def test_url_path_points_to_the_tag(self):
        self.assertEqual(self.tag.url_path, self.url)

    def test_deleting_member_removes_their_tags(self):
        tag_pk = self.tag.pk
        self.user.delete()
        self.assertFalse(NfcTag.objects.filter(pk=tag_pk).exists())
