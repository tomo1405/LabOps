"""会議室予約のテスト。"""

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from community.models import MeetingRoom, RoomReservation

User = get_user_model()


def at(day, hour: int, minute: int = 0):
    return timezone.make_aware(datetime.combine(day, time(hour=hour, minute=minute)))


class RoomReservationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")
        cls.mate = User.objects.create_user(email="mate@example.com", password="pw12345!", name="同僚")
        cls.staff = User.objects.create_user(
            email="staff@example.com", password="pw12345!", name="管理者", is_staff=True
        )
        cls.room = MeetingRoom.objects.create(name="会議室A", location="3階")
        cls.other_room = MeetingRoom.objects.create(name="会議室B")

    def setUp(self):
        self.client.force_login(self.user)
        self.today = timezone.localdate()

    def _reserve(self, start_hour=13, end_hour=14, room=None, purpose="研究ミーティング", day=None):
        day = day or self.today
        return self.client.post(
            reverse("community:reservation_create"),
            {
                "room": (room or self.room).pk,
                "purpose": purpose,
                "start_at": at(day, start_hour).strftime("%Y-%m-%dT%H:%M"),
                "end_at": at(day, end_hour).strftime("%Y-%m-%dT%H:%M"),
                "date": day.isoformat(),
            },
        )

    def _existing(self, start_hour=13, end_hour=14, user=None, room=None):
        return RoomReservation.objects.create(
            room=room or self.room,
            user=user or self.user,
            purpose="既存の予定",
            start_at=at(self.today, start_hour),
            end_at=at(self.today, end_hour),
        )

    # --- 予約する ---

    def test_reserve_records_the_current_user(self):
        response = self._reserve()
        self.assertEqual(response.status_code, 302)
        reservation = RoomReservation.objects.get()
        self.assertEqual(reservation.user, self.user)
        self.assertEqual(reservation.room, self.room)
        self.assertEqual(reservation.purpose, "研究ミーティング")

    def test_reserve_requires_login(self):
        self.client.logout()
        url = reverse("community:reservation_create")
        response = self.client.post(url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}")

    def test_end_must_be_after_start(self):
        response = self._reserve(start_hour=14, end_hour=13)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(RoomReservation.objects.exists())

    def test_same_start_and_end_is_rejected(self):
        response = self._reserve(start_hour=13, end_hour=13)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(RoomReservation.objects.exists())

    # --- 重なりの判定 ---

    def test_overlapping_reservation_is_rejected(self):
        self._existing(13, 15)
        response = self._reserve(start_hour=14, end_hour=16)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "すでに予約されています", status_code=400)
        self.assertEqual(RoomReservation.objects.count(), 1)

    def test_reservation_inside_another_is_rejected(self):
        self._existing(13, 17)
        response = self._reserve(start_hour=14, end_hour=15)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(RoomReservation.objects.count(), 1)

    def test_reservation_covering_another_is_rejected(self):
        self._existing(14, 15)
        response = self._reserve(start_hour=13, end_hour=17)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(RoomReservation.objects.count(), 1)

    def test_touching_times_are_allowed(self):
        """前の予約の終了時刻と、次の予約の開始時刻が同じ場合は重ならない。"""
        self._existing(13, 14)
        response = self._reserve(start_hour=14, end_hour=15)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RoomReservation.objects.count(), 2)

    def test_other_room_at_the_same_time_is_allowed(self):
        self._existing(13, 15)
        response = self._reserve(start_hour=13, end_hour=15, room=self.other_room)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RoomReservation.objects.count(), 2)

    def test_same_time_on_another_day_is_allowed(self):
        self._existing(13, 15)
        response = self._reserve(start_hour=13, end_hour=15, day=self.today + timedelta(days=1))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RoomReservation.objects.count(), 2)

    # --- 表示 ---

    def test_attendance_page_lists_todays_reservations(self):
        self._existing(13, 14)
        response = self.client.get(reverse("community:attendance_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "会議室A")
        self.assertContains(response, "既存の予定")

    def test_attendance_page_shows_other_days_by_date(self):
        tomorrow = self.today + timedelta(days=1)
        RoomReservation.objects.create(
            room=self.room,
            user=self.user,
            purpose="明日の打ち合わせ",
            start_at=at(tomorrow, 10),
            end_at=at(tomorrow, 11),
        )
        response = self.client.get(reverse("community:attendance_list"))
        self.assertNotContains(response, "明日の打ち合わせ")

        response = self.client.get(reverse("community:attendance_list"), {"date": tomorrow.isoformat()})
        self.assertContains(response, "明日の打ち合わせ")

    def test_invalid_date_falls_back_to_today(self):
        response = self.client.get(reverse("community:attendance_list"), {"date": "2026-13-45"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["reservation_day"], self.today)

    def test_form_offers_only_active_rooms(self):
        self.other_room.is_active = False
        self.other_room.save(update_fields=["is_active"])
        response = self.client.get(reverse("community:attendance_list"))
        rooms = response.context["reservation_form"].fields["room"].queryset
        self.assertIn(self.room, rooms)
        self.assertNotIn(self.other_room, rooms)

    def test_page_guides_when_no_room_is_registered(self):
        MeetingRoom.objects.all().delete()
        response = self.client.get(reverse("community:attendance_list"))
        self.assertContains(response, "会議室が登録されていません")

    # --- 取り消し ---

    def test_owner_can_cancel(self):
        reservation = self._existing()
        response = self.client.post(reverse("community:reservation_delete", args=[reservation.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(RoomReservation.objects.exists())

    def test_other_member_cannot_cancel(self):
        reservation = self._existing(user=self.mate)
        response = self.client.post(reverse("community:reservation_delete", args=[reservation.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(RoomReservation.objects.exists())

    def test_staff_can_cancel_any_reservation(self):
        reservation = self._existing(user=self.mate)
        self.client.force_login(self.staff)
        response = self.client.post(reverse("community:reservation_delete", args=[reservation.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(RoomReservation.objects.exists())

    def test_cancel_button_is_hidden_for_other_members(self):
        reservation = self._existing(user=self.mate)
        response = self.client.get(reverse("community:attendance_list"))
        self.assertNotContains(response, reverse("community:reservation_delete", args=[reservation.pk]))

    def test_cancel_rejects_get(self):
        reservation = self._existing()
        response = self.client.get(reverse("community:reservation_delete", args=[reservation.pk]))
        self.assertEqual(response.status_code, 405)

    # --- 付帯 ---

    def test_deleting_room_removes_its_reservations(self):
        self._existing()
        self.room.delete()
        self.assertFalse(RoomReservation.objects.exists())

    def test_is_ongoing_reflects_current_time(self):
        now = timezone.now()
        ongoing = RoomReservation.objects.create(
            room=self.room,
            user=self.user,
            purpose="いま使用中",
            start_at=now - timedelta(minutes=10),
            end_at=now + timedelta(minutes=10),
        )
        later = RoomReservation.objects.create(
            room=self.other_room,
            user=self.user,
            purpose="これから",
            start_at=now + timedelta(hours=1),
            end_at=now + timedelta(hours=2),
        )
        self.assertTrue(ongoing.is_ongoing)
        self.assertFalse(later.is_ongoing)
