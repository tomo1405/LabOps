"""優先度1: 研究支援系モデルの単体テスト。"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from research.models import (
    ConferenceChecklistItem,
    ConferencePrep,
    DiaryEntry,
    EventType,
    ScheduleEvent,
)

User = get_user_model()


class DiaryEntryModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="s1@example.com", password="pw", name="学生A")

    def test_tag_list_splits_and_strips(self):
        entry = DiaryEntry.objects.create(
            user=self.user, date=timezone.localdate(), content="本文", tags=" 実験 , 論文読み ,"
        )
        self.assertEqual(entry.tag_list(), ["実験", "論文読み"])

    def test_tag_list_is_empty_when_no_tags(self):
        entry = DiaryEntry.objects.create(user=self.user, date=timezone.localdate(), content="本文")
        self.assertEqual(entry.tag_list(), [])

    def test_ordering_is_newest_first(self):
        today = timezone.localdate()
        old = DiaryEntry.objects.create(user=self.user, date=today - timedelta(days=3), content="古い")
        new = DiaryEntry.objects.create(user=self.user, date=today, content="新しい")
        self.assertEqual(list(DiaryEntry.objects.all()), [new, old])


class ConferencePrepModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="s2@example.com", password="pw", name="学生B")

    def _prep(self, days_from_today: int) -> ConferencePrep:
        return ConferencePrep.objects.create(
            conference_name="テスト学会",
            deadline=timezone.localdate() + timedelta(days=days_from_today),
            user=self.user,
        )

    def test_days_until_deadline(self):
        self.assertEqual(self._prep(5).days_until_deadline, 5)

    def test_deadline_near_within_warning_window(self):
        prep = self._prep(ConferencePrep.DEADLINE_WARNING_DAYS)
        self.assertTrue(prep.is_deadline_near)
        self.assertFalse(prep.is_overdue)

    def test_deadline_not_near_beyond_warning_window(self):
        prep = self._prep(ConferencePrep.DEADLINE_WARNING_DAYS + 1)
        self.assertFalse(prep.is_deadline_near)

    def test_deadline_today_is_near(self):
        self.assertTrue(self._prep(0).is_deadline_near)

    def test_overdue_deadline_is_not_near(self):
        prep = self._prep(-1)
        self.assertTrue(prep.is_overdue)
        self.assertFalse(prep.is_deadline_near)

    def test_progress_percent_without_items_is_zero(self):
        self.assertEqual(self._prep(3).progress_percent, 0)

    def test_progress_percent_counts_done_items(self):
        prep = self._prep(3)
        ConferenceChecklistItem.objects.create(conference=prep, item="要旨", done=True)
        ConferenceChecklistItem.objects.create(conference=prep, item="スライド", done=False)
        ConferenceChecklistItem.objects.create(conference=prep, item="発表練習", done=False)
        self.assertEqual(prep.progress_percent, 33)


class ScheduleEventModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="s3@example.com", password="pw", name="学生C")

    def test_event_without_user_is_shared(self):
        event = ScheduleEvent.objects.create(title="ゼミ", start_at=timezone.now(), event_type=EventType.TASK)
        self.assertTrue(event.is_shared)

    def test_event_with_user_is_not_shared(self):
        event = ScheduleEvent.objects.create(
            user=self.user, title="実験", start_at=timezone.now(), event_type=EventType.MILESTONE
        )
        self.assertFalse(event.is_shared)

    def test_conference_deletion_keeps_event(self):
        """学会準備を削除しても、紐付いた予定は残る（on_delete=SET_NULL）。"""
        prep = ConferencePrep.objects.create(
            conference_name="学会", deadline=timezone.localdate(), user=self.user
        )
        event = ScheduleEvent.objects.create(
            user=self.user,
            title="原稿締切",
            start_at=timezone.now(),
            event_type=EventType.MILESTONE,
            conference=prep,
        )
        prep.delete()
        event.refresh_from_db()
        self.assertIsNone(event.conference)
