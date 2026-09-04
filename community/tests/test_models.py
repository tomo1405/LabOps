"""優先度2: 情報共有・コミュニケーション系モデルのテスト（詳細設計書 2.2 / 2.9 / 2.10）。"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from community.models import (
    AttendanceState,
    AttendanceStatus,
    CanteenMenu,
    NewsPost,
    NewsStatus,
)

User = get_user_model()


class AttendanceStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")

    def test_default_is_absent(self):
        status = AttendanceStatus.objects.create(user=self.user)
        self.assertEqual(status.status, AttendanceState.ABSENT)
        self.assertFalse(status.is_present)

    def test_toggle_flips_state(self):
        status = AttendanceStatus.objects.create(user=self.user)
        status.toggle()
        self.assertTrue(status.is_present)
        status.toggle()
        self.assertFalse(status.is_present)

    def test_toggle_updates_timestamp(self):
        """toggle() の update_fields に updated_at が含まれ、更新日時が現在時刻になる。"""
        status = AttendanceStatus.objects.create(user=self.user)
        stale = timezone.now() - timedelta(hours=3)
        # auto_now を迂回して、意図的に古い更新日時を書き込む
        AttendanceStatus.objects.filter(pk=status.pk).update(updated_at=stale)
        status.refresh_from_db()

        status.toggle()
        status.refresh_from_db()
        self.assertGreater(status.updated_at, stale)

    def test_one_status_per_user(self):
        AttendanceStatus.objects.create(user=self.user)
        with self.assertRaises(IntegrityError):
            AttendanceStatus.objects.create(user=self.user)


class CanteenMenuTests(TestCase):
    def test_date_is_unique(self):
        today = timezone.localdate()
        CanteenMenu.objects.create(date=today, menu_text="A定食")
        with self.assertRaises(IntegrityError):
            CanteenMenu.objects.create(date=today, menu_text="B定食")

    def test_ordering_is_newest_first(self):
        today = timezone.localdate()
        CanteenMenu.objects.create(date=today - timedelta(days=1), menu_text="昨日")
        CanteenMenu.objects.create(date=today, menu_text="今日")
        self.assertEqual([m.menu_text for m in CanteenMenu.objects.all()], ["今日", "昨日"])


class NewsPostTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")

    def test_default_is_draft(self):
        post = NewsPost.objects.create(title="お知らせ", body="本文", author=self.user)
        self.assertEqual(post.status, NewsStatus.DRAFT)
        self.assertIsNone(post.published_at)
        self.assertFalse(post.is_published)

    def test_publish_sets_status_and_timestamp(self):
        post = NewsPost.objects.create(title="お知らせ", body="本文", author=self.user)
        post.publish()
        post.refresh_from_db()
        self.assertEqual(post.status, NewsStatus.PUBLISHED)
        self.assertIsNotNone(post.published_at)

    def test_publish_is_idempotent(self):
        """公開済みの記事を再度公開しても、公開日時は変わらない。"""
        post = NewsPost.objects.create(title="お知らせ", body="本文", author=self.user)
        post.publish()
        first_published_at = post.published_at
        post.publish()
        post.refresh_from_db()
        self.assertEqual(post.published_at, first_published_at)
