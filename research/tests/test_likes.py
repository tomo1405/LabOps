"""研究日記のいいねのテスト。"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from research.models import DiaryEntry, DiaryVisibility

User = get_user_model()


class DiaryLikeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")
        cls.other = User.objects.create_user(email="other@example.com", password="pw12345!", name="他人")

    def setUp(self):
        self.client.force_login(self.user)
        self.public = DiaryEntry.objects.create(
            user=self.other,
            date=timezone.localdate(),
            content="他人の公開日記",
            visibility=DiaryVisibility.LAB,
        )
        self.private = DiaryEntry.objects.create(
            user=self.other, date=timezone.localdate(), content="他人の非公開日記"
        )

    def _toggle(self, entry):
        return self.client.post(reverse("research:diary_like_toggle", args=[entry.pk]))

    def test_like_adds_current_user(self):
        response = self._toggle(self.public)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.public.like_count, 1)
        self.assertTrue(self.public.is_liked_by(self.user))

    def test_liking_twice_removes_the_like(self):
        self._toggle(self.public)
        self._toggle(self.public)
        self.assertEqual(self.public.like_count, 0)
        self.assertFalse(self.public.is_liked_by(self.user))

    def test_like_is_counted_once_per_user(self):
        """同じ人が何度押しても、いいねは1件を超えない。"""
        self._toggle(self.public)
        self.public.likes.add(self.user)
        self.assertEqual(self.public.like_count, 1)

    def test_multiple_users_can_like_the_same_entry(self):
        self._toggle(self.public)
        self.client.force_login(self.other)
        self._toggle(self.public)
        self.assertEqual(self.public.like_count, 2)

    def test_cannot_like_other_members_private_entry(self):
        response = self._toggle(self.private)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.private.like_count, 0)

    def test_can_like_own_entry(self):
        entry = DiaryEntry.objects.create(user=self.user, date=timezone.localdate(), content="自分の日記")
        self._toggle(entry)
        self.assertEqual(entry.like_count, 1)

    def test_detail_shows_button_state(self):
        response = self.client.get(reverse("research:diary_detail", args=[self.public.pk]))
        self.assertContains(response, 'aria-pressed="false"')

        self._toggle(self.public)
        response = self.client.get(reverse("research:diary_detail", args=[self.public.pk]))
        self.assertContains(response, 'aria-pressed="true"')

    def test_detail_lists_who_liked(self):
        self.client.force_login(self.other)
        self._toggle(self.public)
        self.client.force_login(self.user)
        response = self.client.get(reverse("research:diary_detail", args=[self.public.pk]))
        self.assertContains(response, "他人")

    def test_list_shows_like_count(self):
        self._toggle(self.public)
        response = self.client.get(reverse("research:diary_list"), {"scope": "lab"})
        self.assertContains(response, "★ 1")

    def test_list_hides_count_when_no_likes(self):
        response = self.client.get(reverse("research:diary_list"), {"scope": "lab"})
        self.assertNotContains(response, 'title="いいね"')

    def test_deleting_entry_removes_likes(self):
        entry = DiaryEntry.objects.create(user=self.user, date=timezone.localdate(), content="自分の日記")
        self._toggle(entry)
        self.assertEqual(self.user.liked_diaries.count(), 1)
        self.client.post(reverse("research:diary_delete", args=[entry.pk]))
        self.assertEqual(self.user.liked_diaries.count(), 0)

    def test_like_rejects_get(self):
        response = self.client.get(reverse("research:diary_like_toggle", args=[self.public.pk]))
        self.assertEqual(response.status_code, 405)

    def test_like_requires_login(self):
        self.client.logout()
        url = reverse("research:diary_like_toggle", args=[self.public.pk])
        response = self.client.post(url)
        self.assertRedirects(response, f"{reverse('accounts:login')}?next={url}")
