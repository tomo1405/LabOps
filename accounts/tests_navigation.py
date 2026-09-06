"""ナビゲーションの現在地表示のテスト。"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from community.models import CanteenMenu, NewsPost
from research.models import ConferencePrep, DiaryEntry, EventType, ScheduleEvent

User = get_user_model()


class NavigationActiveTests(TestCase):
    """開いている画面に対応するメニューだけが選択状態になる。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")

    def setUp(self):
        self.client.force_login(self.user)

    def _active_labels(self, url: str) -> list[str]:
        """レスポンスHTMLから、active が付いたメニューのラベルを取り出す。"""
        html = self.client.get(url).content.decode()
        labels = []
        for label in ("ホーム", "研究日記", "スケジュール", "学会準備", "在室", "学食", "News"):
            marker = f'aria-current="page">{label}</a>'
            if marker in html:
                labels.append(label)
        return labels

    def test_dashboard_marks_home_only(self):
        self.assertEqual(self._active_labels(reverse("research:dashboard")), ["ホーム"])

    def test_diary_list_marks_diary_only(self):
        self.assertEqual(self._active_labels(reverse("research:diary_list")), ["研究日記"])

    def test_diary_detail_keeps_parent_menu_active(self):
        """詳細画面でも親メニューが選択状態のままになる。"""
        entry = DiaryEntry.objects.create(user=self.user, date=timezone.localdate(), content="記録")
        self.assertEqual(self._active_labels(reverse("research:diary_detail", args=[entry.pk])), ["研究日記"])

    def test_diary_edit_keeps_parent_menu_active(self):
        entry = DiaryEntry.objects.create(user=self.user, date=timezone.localdate(), content="記録")
        self.assertEqual(self._active_labels(reverse("research:diary_update", args=[entry.pk])), ["研究日記"])

    def test_schedule_marks_schedule_only(self):
        self.assertEqual(self._active_labels(reverse("research:schedule")), ["スケジュール"])

    def test_schedule_edit_keeps_parent_menu_active(self):
        event = ScheduleEvent.objects.create(
            user=self.user,
            title="ゼミ",
            start_at=timezone.now(),
            event_type=EventType.TASK,
        )
        self.assertEqual(
            self._active_labels(reverse("research:schedule_event_update", args=[event.pk])),
            ["スケジュール"],
        )

    def test_conference_marks_conference_only(self):
        self.assertEqual(self._active_labels(reverse("research:conference_list")), ["学会準備"])

    def test_conference_edit_keeps_parent_menu_active(self):
        prep = ConferencePrep.objects.create(
            conference_name="テスト学会", deadline=timezone.localdate(), user=self.user
        )
        self.assertEqual(
            self._active_labels(reverse("research:conference_update", args=[prep.pk])), ["学会準備"]
        )

    def test_attendance_marks_attendance_only(self):
        self.assertEqual(self._active_labels(reverse("community:attendance_list")), ["在室"])

    def test_canteen_marks_canteen_only(self):
        self.assertEqual(self._active_labels(reverse("community:canteen_today")), ["学食"])

    def test_canteen_edit_keeps_parent_menu_active(self):
        menu = CanteenMenu.objects.create(date=timezone.localdate(), menu_text="A定食")
        self.assertEqual(self._active_labels(reverse("community:canteen_update", args=[menu.pk])), ["学食"])

    def test_news_marks_news_only(self):
        self.assertEqual(self._active_labels(reverse("community:news_list")), ["News"])

    def test_news_edit_keeps_parent_menu_active(self):
        post = NewsPost.objects.create(title="お知らせ", body="本文", author=self.user)
        self.assertEqual(self._active_labels(reverse("community:news_update", args=[post.pk])), ["News"])

    def test_admin_link_is_hidden_for_normal_members(self):
        """管理画面のリンクは、管理画面を使えない人には出さない。"""
        response = self.client.get(reverse("research:dashboard"))
        self.assertNotContains(response, reverse("admin:index"))

    def test_admin_link_is_shown_to_staff(self):
        staff = User.objects.create_user(
            email="staff@example.com", password="pw12345!", name="管理者", is_staff=True
        )
        self.client.force_login(staff)
        response = self.client.get(reverse("research:dashboard"))
        self.assertContains(response, reverse("admin:index"))
        self.assertContains(response, "管理画面")

    def test_sub_page_shows_breadcrumb_to_parent(self):
        entry = DiaryEntry.objects.create(user=self.user, date=timezone.localdate(), content="記録")
        response = self.client.get(reverse("research:diary_detail", args=[entry.pk]))
        self.assertContains(response, 'aria-label="現在の位置"')
        self.assertContains(response, reverse("research:diary_list"))
