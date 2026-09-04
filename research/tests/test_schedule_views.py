"""研究スケジュールの表示単位（月・週・日）と参加者のテスト。"""

from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from research.models import EventType, ScheduleEvent

User = get_user_model()


def at(day: date, hour: int) -> datetime:
    return timezone.make_aware(datetime.combine(day, time(hour=hour)))


class ScheduleViewSwitchTests(TestCase):
    """view=month|week|day で表示範囲が切り替わる。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")
        # 2026-09-09 は水曜日。週は日曜(9/6)〜土曜(9/12)
        cls.anchor = date(2026, 9, 9)

    def setUp(self):
        self.client.force_login(self.user)
        for day, title in (
            (date(2026, 9, 9), "当日の予定"),
            (date(2026, 9, 11), "同じ週の予定"),
            (date(2026, 9, 20), "同じ月の別週の予定"),
            (date(2026, 10, 1), "翌月の予定"),
        ):
            ScheduleEvent.objects.create(
                user=self.user, title=title, start_at=at(day, 10), event_type=EventType.TASK
            )

    def _titles(self, **params) -> set[str]:
        response = self.client.get(reverse("research:schedule"), params)
        self.assertEqual(response.status_code, 200)
        return {event.title for event in response.context["events"]}

    def test_day_view_shows_only_that_day(self):
        self.assertEqual(self._titles(view="day", date=self.anchor.isoformat()), {"当日の予定"})

    def test_week_view_shows_sunday_to_saturday(self):
        self.assertEqual(
            self._titles(view="week", date=self.anchor.isoformat()),
            {"当日の予定", "同じ週の予定"},
        )

    def test_month_view_shows_whole_month(self):
        self.assertEqual(
            self._titles(view="month", date=self.anchor.isoformat()),
            {"当日の予定", "同じ週の予定", "同じ月の別週の予定"},
        )

    def test_default_view_is_month(self):
        response = self.client.get(reverse("research:schedule"))
        self.assertEqual(response.context["view"], "month")

    def test_unknown_view_falls_back_to_month(self):
        response = self.client.get(reverse("research:schedule"), {"view": "year"})
        self.assertEqual(response.context["view"], "month")

    def test_legacy_year_month_parameters_still_work(self):
        response = self.client.get(reverse("research:schedule"), {"year": 2026, "month": 10})
        self.assertEqual({e.title for e in response.context["events"]}, {"翌月の予定"})

    def test_invalid_date_returns_404(self):
        response = self.client.get(reverse("research:schedule"), {"date": "2026-13-45"})
        self.assertEqual(response.status_code, 404)

    def test_invalid_month_returns_404(self):
        response = self.client.get(reverse("research:schedule"), {"year": 2026, "month": 13})
        self.assertEqual(response.status_code, 404)

    def test_navigation_moves_by_one_period(self):
        response = self.client.get(
            reverse("research:schedule"), {"view": "day", "date": self.anchor.isoformat()}
        )
        self.assertIn("date=2026-09-08", response.context["prev_url"])
        self.assertIn("date=2026-09-10", response.context["next_url"])

        response = self.client.get(
            reverse("research:schedule"), {"view": "week", "date": self.anchor.isoformat()}
        )
        self.assertIn("date=2026-09-02", response.context["prev_url"])
        self.assertIn("date=2026-09-16", response.context["next_url"])

        response = self.client.get(
            reverse("research:schedule"), {"view": "month", "date": self.anchor.isoformat()}
        )
        self.assertIn("date=2026-08-01", response.context["prev_url"])
        self.assertIn("date=2026-10-01", response.context["next_url"])

    def test_week_view_lists_seven_days(self):
        response = self.client.get(
            reverse("research:schedule"), {"view": "week", "date": self.anchor.isoformat()}
        )
        days = response.context["days"]
        self.assertEqual(len(days), 7)
        self.assertEqual(days[0]["date"], date(2026, 9, 6))
        self.assertEqual(days[-1]["date"], date(2026, 9, 12))

    def test_day_view_lists_one_day(self):
        response = self.client.get(
            reverse("research:schedule"), {"view": "day", "date": self.anchor.isoformat()}
        )
        self.assertEqual(len(response.context["days"]), 1)
        self.assertEqual(response.context["days"][0]["date"], self.anchor)


class ScheduleEventTypeTests(TestCase):
    """種別（予定・タスク・マイルストーン）。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")

    def setUp(self):
        self.client.force_login(self.user)

    def test_three_types_are_available(self):
        self.assertEqual(
            [(value, label) for value, label in EventType.choices],
            [("appointment", "予定"), ("task", "タスク"), ("milestone", "マイルストーン")],
        )

    def test_default_type_is_appointment(self):
        """種別を指定せずに作った予定は「予定」になる。"""
        event = ScheduleEvent.objects.create(
            user=self.user, title="打ち合わせ", start_at=at(timezone.localdate(), 10)
        )
        self.assertEqual(event.event_type, EventType.APPOINTMENT)
        self.assertEqual(event.get_event_type_display(), "予定")

    def test_create_event_with_appointment_type(self):
        start = timezone.localtime(timezone.now() + timedelta(days=1))
        self.client.post(
            reverse("research:schedule_event_create"),
            {
                "title": "指導教員との面談",
                "start_at": start.strftime("%Y-%m-%dT%H:%M"),
                "end_at": "",
                "event_type": EventType.APPOINTMENT,
                "conference": "",
            },
        )
        event = ScheduleEvent.objects.get(title="指導教員との面談")
        self.assertEqual(event.event_type, EventType.APPOINTMENT)

    def test_form_offers_appointment_as_initial_choice(self):
        response = self.client.get(reverse("research:schedule"))
        html = response.content.decode()
        self.assertIn('<option value="appointment"', html)
        self.assertIn(">予定</option>", html)

    def test_type_is_reflected_in_display_class(self):
        """カレンダー上の色分けに使うクラス名が種別ごとに変わる。"""
        for event_type, expected in (
            (EventType.APPOINTMENT, "schedule-slot appointment"),
            (EventType.TASK, "schedule-slot task"),
            (EventType.MILESTONE, "schedule-slot milestone"),
        ):
            with self.subTest(event_type=event_type):
                ScheduleEvent.objects.all().delete()
                ScheduleEvent.objects.create(
                    user=self.user,
                    title="種別の確認",
                    start_at=at(timezone.localdate(), 10),
                    event_type=event_type,
                )
                response = self.client.get(reverse("research:schedule"), {"view": "day"})
                self.assertIn(expected, response.content.decode())


class ScheduleWeekLayoutTests(TestCase):
    """週表示は列が狭いため、日表示とは出し分ける（レイアウト崩れ対策）。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")
        cls.mate = User.objects.create_user(email="mate@example.com", password="pw12345!", name="同僚")

    def setUp(self):
        self.client.force_login(self.user)
        self.event = ScheduleEvent.objects.create(
            user=self.user,
            title="打ち合わせ",
            start_at=at(timezone.localdate(), 10),
            event_type=EventType.TASK,
        )
        self.event.participants.add(self.mate)

    def _html(self, view: str) -> str:
        response = self.client.get(reverse("research:schedule"), {"view": view})
        return response.content.decode()

    def test_today_badge_only_in_day_view(self):
        """週表示では「今日」バッジを出さない（列が狭く折り返して崩れるため）。"""
        self.assertNotIn('<span class="badge text-bg-primary">今日</span>', self._html("week"))
        self.assertIn('<span class="badge text-bg-primary">今日</span>', self._html("day"))

    def test_today_column_is_still_marked_in_week_view(self):
        """バッジを出さない代わりに、今日の列には today クラスが付く。"""
        self.assertIn('class="schedule-day today"', self._html("week"))

    def test_participants_are_summarised_in_week_view(self):
        """週表示は人数のみ、日表示は氏名を出す。"""
        week = self._html("week")
        self.assertIn("参加 1人", week)
        self.assertNotIn("参加 同僚", week)

        day = self._html("day")
        self.assertIn("同僚", day)


class ScheduleParticipantTests(TestCase):
    """参加者に指定された人のスケジュールにも予定が出る。"""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(email="owner@example.com", password="pw12345!", name="主催者")
        cls.member = User.objects.create_user(email="member@example.com", password="pw12345!", name="参加者")
        cls.stranger = User.objects.create_user(
            email="stranger@example.com", password="pw12345!", name="無関係"
        )

    def _create_meeting(self) -> ScheduleEvent:
        event = ScheduleEvent.objects.create(
            user=self.owner,
            title="打ち合わせ",
            start_at=timezone.now() + timedelta(days=1),
            event_type=EventType.TASK,
        )
        event.participants.add(self.member)
        return event

    def test_participant_sees_event_in_schedule(self):
        self._create_meeting()
        self.client.force_login(self.member)
        response = self.client.get(reverse("research:schedule"))
        self.assertEqual({e.title for e in response.context["events"]}, {"打ち合わせ"})

    def test_unrelated_member_does_not_see_event(self):
        self._create_meeting()
        self.client.force_login(self.stranger)
        response = self.client.get(reverse("research:schedule"))
        self.assertEqual(list(response.context["events"]), [])

    def test_participant_sees_event_on_dashboard(self):
        self._create_meeting()
        self.client.force_login(self.member)
        response = self.client.get(reverse("research:dashboard"))
        self.assertEqual({e.title for e in response.context["upcoming_events"]}, {"打ち合わせ"})

    def test_participant_cannot_edit_or_delete(self):
        """参加者に追加されただけの人は、他人の予定を書き換えられない。"""
        event = self._create_meeting()
        self.client.force_login(self.member)
        for name in ("research:schedule_event_update", "research:schedule_event_delete"):
            with self.subTest(view=name):
                response = self.client.get(reverse(name, args=[event.pk]))
                self.assertEqual(response.status_code, 404)

    def test_owner_can_add_participants_on_create(self):
        self.client.force_login(self.owner)
        start = timezone.localtime(timezone.now() + timedelta(days=2))
        self.client.post(
            reverse("research:schedule_event_create"),
            {
                "title": "ゼミ打ち合わせ",
                "start_at": start.strftime("%Y-%m-%dT%H:%M"),
                "end_at": "",
                "event_type": EventType.TASK,
                "conference": "",
                "participants": [self.member.pk],
                "view": "week",
            },
        )
        event = ScheduleEvent.objects.get(title="ゼミ打ち合わせ")
        self.assertEqual([u.name for u in event.participants.all()], ["参加者"])

    def test_owner_can_change_participants_on_edit(self):
        event = self._create_meeting()
        self.client.force_login(self.owner)
        start = timezone.localtime(event.start_at)
        self.client.post(
            reverse("research:schedule_event_update", args=[event.pk]),
            {
                "title": "打ち合わせ",
                "start_at": start.strftime("%Y-%m-%dT%H:%M"),
                "end_at": "",
                "event_type": EventType.TASK,
                "conference": "",
                "participants": [self.stranger.pk],
            },
        )
        self.assertEqual([u.name for u in event.participants.all()], ["無関係"])

    def test_participant_choices_exclude_self(self):
        """参加者の候補に自分は出ない（作成者は常に予定に含まれるため）。"""
        self.client.force_login(self.owner)
        response = self.client.get(reverse("research:schedule"))
        choices = response.context["form"].fields["participants"].queryset
        self.assertNotIn(self.owner, choices)
        self.assertIn(self.member, choices)

    def test_event_is_not_duplicated_for_participant_owner(self):
        """自分の予定に自分が参加者として入っていても、一覧に重複表示されない。"""
        event = self._create_meeting()
        event.participants.add(self.owner)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("research:schedule"))
        self.assertEqual(len(response.context["events"]), 1)
