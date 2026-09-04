"""研究日記のコメントのテスト。"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from research.models import DiaryComment, DiaryEntry, DiaryVisibility

User = get_user_model()


class DiaryCommentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")
        cls.other = User.objects.create_user(email="other@example.com", password="pw12345!", name="他人")

    def setUp(self):
        self.client.force_login(self.user)
        self.own = DiaryEntry.objects.create(user=self.user, date=timezone.localdate(), content="自分の日記")
        self.public = DiaryEntry.objects.create(
            user=self.other,
            date=timezone.localdate(),
            content="他人の公開日記",
            visibility=DiaryVisibility.LAB,
        )
        self.private = DiaryEntry.objects.create(
            user=self.other, date=timezone.localdate(), content="他人の非公開日記"
        )

    def _post(self, entry, body="参考になりました"):
        return self.client.post(reverse("research:diary_comment_create", args=[entry.pk]), {"body": body})

    def test_comment_on_public_entry(self):
        response = self._post(self.public)
        self.assertRedirects(response, reverse("research:diary_detail", args=[self.public.pk]))
        comment = DiaryComment.objects.get()
        self.assertEqual(comment.diary, self.public)
        self.assertEqual(comment.author, self.user)

    def test_comment_on_own_entry(self):
        self._post(self.own, body="自分用のメモ")
        self.assertEqual(self.own.comments.count(), 1)

    def test_cannot_comment_on_other_members_private_entry(self):
        response = self._post(self.private)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(DiaryComment.objects.exists())

    def test_empty_comment_is_rejected(self):
        response = self._post(self.public, body="")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DiaryComment.objects.exists())

    def test_comments_are_shown_in_posted_order(self):
        self._post(self.public, body="1つ目")
        self._post(self.public, body="2つ目")
        response = self.client.get(reverse("research:diary_detail", args=[self.public.pk]))
        bodies = [c.body for c in response.context["entry"].comments.all()]
        self.assertEqual(bodies, ["1つ目", "2つ目"])

    def test_author_can_delete_own_comment(self):
        self._post(self.public)
        comment = DiaryComment.objects.get()
        response = self.client.post(
            reverse("research:diary_comment_delete", args=[self.public.pk, comment.pk])
        )
        self.assertRedirects(response, reverse("research:diary_detail", args=[self.public.pk]))
        self.assertFalse(DiaryComment.objects.exists())

    def test_diary_owner_can_delete_others_comment(self):
        """自分の日記に付いたコメントは、日記の作成者も削除できる。"""
        comment = DiaryComment.objects.create(diary=self.own, author=self.other, body="他人からのコメント")
        response = self.client.post(reverse("research:diary_comment_delete", args=[self.own.pk, comment.pk]))
        self.assertRedirects(response, reverse("research:diary_detail", args=[self.own.pk]))
        self.assertFalse(DiaryComment.objects.exists())

    def test_cannot_delete_unrelated_comment(self):
        """他人の日記に付いた他人のコメントは削除できない。"""
        comment = DiaryComment.objects.create(diary=self.public, author=self.other, body="他人同士のやり取り")
        response = self.client.post(
            reverse("research:diary_comment_delete", args=[self.public.pk, comment.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(DiaryComment.objects.filter(pk=comment.pk).exists())

    def test_deleting_entry_removes_comments(self):
        DiaryComment.objects.create(diary=self.own, author=self.other, body="コメント")
        self.client.post(reverse("research:diary_delete", args=[self.own.pk]))
        self.assertFalse(DiaryComment.objects.exists())

    def test_comment_create_rejects_get(self):
        response = self.client.get(reverse("research:diary_comment_create", args=[self.public.pk]))
        self.assertEqual(response.status_code, 405)
