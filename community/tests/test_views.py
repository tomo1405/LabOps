"""優先度2: 情報共有・コミュニケーション系ビューのテスト（詳細設計書 4章のエンドポイント）。"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from community.models import (
    AttendanceState,
    AttendanceStatus,
    CanteenMenu,
    MenuSource,
    NewsPost,
    NewsStatus,
)

User = get_user_model()


class LoginRequiredTests(TestCase):
    """未ログインでは全画面がログイン画面へリダイレクトされる。"""

    def test_protected_views_redirect_to_login(self):
        urls = [
            reverse("community:attendance_list"),
            reverse("community:canteen_today"),
            reverse("community:canteen_update", args=[1]),
            reverse("community:canteen_delete", args=[1]),
            reverse("community:news_list"),
            reverse("community:news_create"),
            reverse("community:news_update", args=[1]),
            reverse("community:news_delete", args=[1]),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}")


class AuthenticatedTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")
        cls.other = User.objects.create_user(email="other@example.com", password="pw12345!", name="他人")

    def setUp(self):
        self.client.force_login(self.user)


class AttendanceViewTests(AuthenticatedTestCase):
    def test_list_shows_all_active_members(self):
        response = self.client.get(reverse("community:attendance_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "本人")
        self.assertContains(response, "他人")

    def test_toggle_creates_status_and_marks_present(self):
        response = self.client.post(reverse("community:attendance_toggle"))
        self.assertEqual(response.status_code, 200)
        status = AttendanceStatus.objects.get(user=self.user)
        self.assertEqual(status.status, AttendanceState.PRESENT)

    def test_toggle_twice_returns_to_absent(self):
        self.client.post(reverse("community:attendance_toggle"))
        self.client.post(reverse("community:attendance_toggle"))
        status = AttendanceStatus.objects.get(user=self.user)
        self.assertEqual(status.status, AttendanceState.ABSENT)

    def test_toggle_does_not_touch_other_members(self):
        other_status = AttendanceStatus.objects.create(user=self.other, status=AttendanceState.PRESENT)
        self.client.post(reverse("community:attendance_toggle"))
        other_status.refresh_from_db()
        self.assertEqual(other_status.status, AttendanceState.PRESENT)
        self.assertEqual(AttendanceStatus.objects.filter(user=self.user).count(), 1)

    def test_toggle_rejects_get(self):
        response = self.client.get(reverse("community:attendance_toggle"))
        self.assertEqual(response.status_code, 405)

    def test_present_count_reflects_current_state(self):
        AttendanceStatus.objects.create(user=self.other, status=AttendanceState.PRESENT)
        response = self.client.get(reverse("community:attendance_list"))
        self.assertEqual(response.context["present_count"], 1)


class CanteenViewTests(AuthenticatedTestCase):
    def test_register_today_menu(self):
        today = timezone.localdate()
        response = self.client.post(
            reverse("community:canteen_create"),
            {"date": today.isoformat(), "menu_text": "A定食: からあげ"},
        )
        self.assertRedirects(response, reverse("community:canteen_today"))
        menu = CanteenMenu.objects.get()
        self.assertEqual(menu.menu_text, "A定食: からあげ")
        self.assertEqual(menu.source, MenuSource.MANUAL)

    def test_same_date_overwrites_instead_of_duplicating(self):
        today = timezone.localdate()
        self.client.post(
            reverse("community:canteen_create"),
            {"date": today.isoformat(), "menu_text": "A定食: からあげ"},
        )
        self.client.post(
            reverse("community:canteen_create"),
            {"date": today.isoformat(), "menu_text": "A定食: 焼き魚"},
        )
        self.assertEqual(CanteenMenu.objects.count(), 1)
        self.assertEqual(CanteenMenu.objects.get().menu_text, "A定食: 焼き魚")

    def test_today_view_shows_today_menu_only_in_today_slot(self):
        today = timezone.localdate()
        CanteenMenu.objects.create(date=today, menu_text="本日のメニュー")
        CanteenMenu.objects.create(date=today - timedelta(days=1), menu_text="昨日のメニュー")
        response = self.client.get(reverse("community:canteen_today"))
        self.assertEqual(response.context["today_menu"].menu_text, "本日のメニュー")
        self.assertNotIn(response.context["today_menu"], list(response.context["recent_menus"]))
        self.assertEqual(len(response.context["recent_menus"]), 1)

    def test_empty_menu_text_is_rejected(self):
        response = self.client.post(
            reverse("community:canteen_create"),
            {"date": timezone.localdate().isoformat(), "menu_text": ""},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CanteenMenu.objects.exists())


class CanteenUpdateDeleteTests(AuthenticatedTestCase):
    """学食メニューの更新・削除。日付ごとに1件という制約を保つ。"""

    def setUp(self):
        super().setUp()
        self.today = timezone.localdate()
        self.menu = CanteenMenu.objects.create(date=self.today, menu_text="A定食: からあげ")

    def test_edit_form_shows_current_values(self):
        response = self.client.get(reverse("community:canteen_update", args=[self.menu.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A定食: からあげ")

    def test_update_changes_menu_text(self):
        response = self.client.post(
            reverse("community:canteen_update", args=[self.menu.pk]),
            {"date": self.today.isoformat(), "menu_text": "A定食: 焼き魚"},
        )
        self.assertRedirects(response, reverse("community:canteen_today"))
        self.menu.refresh_from_db()
        self.assertEqual(self.menu.menu_text, "A定食: 焼き魚")
        self.assertEqual(CanteenMenu.objects.count(), 1)

    def test_moving_to_an_existing_date_overwrites_that_day(self):
        """既に登録済みの日付へ移すと、その日の登録を置き換えて重複を作らない。"""
        yesterday = self.today - timedelta(days=1)
        CanteenMenu.objects.create(date=yesterday, menu_text="昨日のメニュー")
        self.client.post(
            reverse("community:canteen_update", args=[self.menu.pk]),
            {"date": yesterday.isoformat(), "menu_text": "差し替え後のメニュー"},
        )
        self.assertEqual(CanteenMenu.objects.count(), 1)
        menu = CanteenMenu.objects.get()
        self.assertEqual(menu.date, yesterday)
        self.assertEqual(menu.menu_text, "差し替え後のメニュー")

    def test_update_rejects_empty_menu_text(self):
        response = self.client.post(
            reverse("community:canteen_update", args=[self.menu.pk]),
            {"date": self.today.isoformat(), "menu_text": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.menu.refresh_from_db()
        self.assertEqual(self.menu.menu_text, "A定食: からあげ")

    def test_delete_confirmation_page_does_not_delete(self):
        response = self.client.get(reverse("community:canteen_delete", args=[self.menu.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(CanteenMenu.objects.filter(pk=self.menu.pk).exists())

    def test_delete_removes_menu(self):
        response = self.client.post(reverse("community:canteen_delete", args=[self.menu.pk]))
        self.assertRedirects(response, reverse("community:canteen_today"))
        self.assertFalse(CanteenMenu.objects.filter(pk=self.menu.pk).exists())


class NewsViewTests(AuthenticatedTestCase):
    def test_save_as_draft_does_not_set_published_at(self):
        response = self.client.post(
            reverse("community:news_create"),
            {"title": "ゼミ日程の変更", "body": "来週のゼミは水曜です。", "draft": ""},
        )
        self.assertRedirects(response, reverse("community:news_list"))
        post = NewsPost.objects.get()
        self.assertEqual(post.status, NewsStatus.DRAFT)
        self.assertIsNone(post.published_at)
        self.assertEqual(post.author, self.user)

    def test_publish_on_create_sets_published_at(self):
        self.client.post(
            reverse("community:news_create"),
            {"title": "受賞のお知らせ", "body": "学会で受賞しました。", "publish": ""},
        )
        post = NewsPost.objects.get()
        self.assertEqual(post.status, NewsStatus.PUBLISHED)
        self.assertIsNotNone(post.published_at)

    def test_publish_existing_draft(self):
        post = NewsPost.objects.create(title="下書き", body="本文", author=self.user)
        response = self.client.post(reverse("community:news_publish", args=[post.pk]))
        self.assertRedirects(response, reverse("community:news_list"))
        post.refresh_from_db()
        self.assertEqual(post.status, NewsStatus.PUBLISHED)

    def test_cannot_publish_other_members_draft(self):
        post = NewsPost.objects.create(title="他人の下書き", body="本文", author=self.other)
        response = self.client.post(reverse("community:news_publish", args=[post.pk]))
        self.assertEqual(response.status_code, 404)
        post.refresh_from_db()
        self.assertEqual(post.status, NewsStatus.DRAFT)

    def test_list_hides_other_members_drafts(self):
        NewsPost.objects.create(title="他人の下書き", body="本文", author=self.other)
        NewsPost.objects.create(
            title="他人の公開記事",
            body="本文",
            author=self.other,
            status=NewsStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        NewsPost.objects.create(title="自分の下書き", body="本文", author=self.user)
        response = self.client.get(reverse("community:news_list"))
        titles = {p.title for p in response.context["posts"]}
        self.assertEqual(titles, {"他人の公開記事", "自分の下書き"})

    def test_publish_rejects_get(self):
        post = NewsPost.objects.create(title="下書き", body="本文", author=self.user)
        response = self.client.get(reverse("community:news_publish", args=[post.pk]))
        self.assertEqual(response.status_code, 405)


class NewsUpdateDeleteTests(AuthenticatedTestCase):
    """News記事の更新・削除・公開の取り下げ。"""

    def setUp(self):
        super().setUp()
        self.draft = NewsPost.objects.create(title="下書き記事", body="本文", author=self.user)

    def test_edit_form_shows_current_values(self):
        response = self.client.get(reverse("community:news_update", args=[self.draft.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "下書き記事")

    def test_update_changes_title_and_body(self):
        response = self.client.post(
            reverse("community:news_update", args=[self.draft.pk]),
            {"title": "変更後のタイトル", "body": "変更後の本文"},
        )
        self.assertRedirects(response, reverse("community:news_list"))
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.title, "変更後のタイトル")
        self.assertEqual(self.draft.body, "変更後の本文")
        self.assertEqual(NewsPost.objects.count(), 1)

    def test_update_keeps_published_state_and_timestamp(self):
        """公開済みの記事を編集しても、公開状態と公開日時は変わらない。"""
        post = NewsPost.objects.create(
            title="公開記事",
            body="本文",
            author=self.user,
            status=NewsStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        published_at = post.published_at
        self.client.post(
            reverse("community:news_update", args=[post.pk]),
            {"title": "公開記事（訂正）", "body": "訂正後の本文"},
        )
        post.refresh_from_db()
        self.assertEqual(post.status, NewsStatus.PUBLISHED)
        self.assertEqual(post.published_at, published_at)

    def test_cannot_edit_other_members_post(self):
        post = NewsPost.objects.create(title="他人の記事", body="本文", author=self.other)
        response = self.client.post(
            reverse("community:news_update", args=[post.pk]),
            {"title": "書き換え", "body": "本文"},
        )
        self.assertEqual(response.status_code, 404)
        post.refresh_from_db()
        self.assertEqual(post.title, "他人の記事")

    def test_delete_confirmation_page_does_not_delete(self):
        response = self.client.get(reverse("community:news_delete", args=[self.draft.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(NewsPost.objects.filter(pk=self.draft.pk).exists())

    def test_delete_removes_post(self):
        response = self.client.post(reverse("community:news_delete", args=[self.draft.pk]))
        self.assertRedirects(response, reverse("community:news_list"))
        self.assertFalse(NewsPost.objects.filter(pk=self.draft.pk).exists())

    def test_cannot_delete_other_members_post(self):
        post = NewsPost.objects.create(title="他人の記事", body="本文", author=self.other)
        response = self.client.post(reverse("community:news_delete", args=[post.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(NewsPost.objects.filter(pk=post.pk).exists())

    def test_unpublish_returns_post_to_draft(self):
        post = NewsPost.objects.create(
            title="公開記事",
            body="本文",
            author=self.user,
            status=NewsStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        response = self.client.post(reverse("community:news_unpublish", args=[post.pk]))
        self.assertRedirects(response, reverse("community:news_list"))
        post.refresh_from_db()
        self.assertEqual(post.status, NewsStatus.DRAFT)
        self.assertIsNone(post.published_at)

    def test_republish_after_unpublish_sets_new_timestamp(self):
        post = NewsPost.objects.create(title="記事", body="本文", author=self.user)
        self.client.post(reverse("community:news_publish", args=[post.pk]))
        self.client.post(reverse("community:news_unpublish", args=[post.pk]))
        self.client.post(reverse("community:news_publish", args=[post.pk]))
        post.refresh_from_db()
        self.assertEqual(post.status, NewsStatus.PUBLISHED)
        self.assertIsNotNone(post.published_at)

    def test_cannot_unpublish_other_members_post(self):
        post = NewsPost.objects.create(
            title="他人の公開記事",
            body="本文",
            author=self.other,
            status=NewsStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        response = self.client.post(reverse("community:news_unpublish", args=[post.pk]))
        self.assertEqual(response.status_code, 404)
        post.refresh_from_db()
        self.assertEqual(post.status, NewsStatus.PUBLISHED)


class DashboardIntegrationTests(AuthenticatedTestCase):
    """ダッシュボードが優先度2の情報も集約する（基本設計書5章）。"""

    def test_dashboard_shows_present_members_menu_and_news(self):
        AttendanceStatus.objects.create(user=self.other, status=AttendanceState.PRESENT)
        CanteenMenu.objects.create(date=timezone.localdate(), menu_text="A定食: カレー")
        NewsPost.objects.create(
            title="公開ニュース",
            body="本文",
            author=self.other,
            status=NewsStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        NewsPost.objects.create(title="下書きニュース", body="本文", author=self.other)

        response = self.client.get(reverse("research:dashboard"))
        self.assertEqual([u.name for u in response.context["present_members"]], ["他人"])
        self.assertEqual(response.context["today_menu"].menu_text, "A定食: カレー")
        self.assertEqual([p.title for p in response.context["latest_news"]], ["公開ニュース"])

    def test_dashboard_excludes_absent_members(self):
        AttendanceStatus.objects.create(user=self.other, status=AttendanceState.ABSENT)
        response = self.client.get(reverse("research:dashboard"))
        self.assertEqual(list(response.context["present_members"]), [])
