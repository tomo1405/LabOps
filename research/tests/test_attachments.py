"""研究日記の添付ファイルのテスト。"""

import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from research.models import DiaryAttachment, DiaryEntry, DiaryVisibility

User = get_user_model()

MEDIA_ROOT = tempfile.mkdtemp(prefix="labops-test-media-")


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class DiaryAttachmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")
        cls.other = User.objects.create_user(email="other@example.com", password="pw12345!", name="他人")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA_ROOT, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.client.force_login(self.user)
        self.entry = DiaryEntry.objects.create(
            user=self.user, date=timezone.localdate(), content="実験の記録"
        )

    def _upload(self, name="graph.png", content=b"binary-data", entry=None):
        return self.client.post(
            reverse("research:diary_attachment_create", args=[(entry or self.entry).pk]),
            {"file": SimpleUploadedFile(name, content)},
        )

    def test_upload_attaches_file_to_entry(self):
        response = self._upload()
        self.assertRedirects(response, reverse("research:diary_detail", args=[self.entry.pk]))
        attachment = DiaryAttachment.objects.get()
        self.assertEqual(attachment.diary, self.entry)
        self.assertEqual(attachment.original_name, "graph.png")

    def test_image_is_flagged_for_inline_display(self):
        self._upload(name="figure.PNG")
        self.assertTrue(DiaryAttachment.objects.get().is_image)

    def test_non_image_is_not_flagged(self):
        self._upload(name="notes.pdf")
        self.assertFalse(DiaryAttachment.objects.get().is_image)

    def test_multiple_attachments_per_entry(self):
        self._upload(name="a.png")
        self._upload(name="b.csv")
        self.assertEqual(self.entry.attachments.count(), 2)

    def test_oversized_file_is_rejected(self):
        oversized = b"x" * (10 * 1024 * 1024 + 1)
        response = self._upload(name="big.bin", content=oversized)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DiaryAttachment.objects.exists())

    def test_cannot_attach_to_other_members_entry(self):
        entry = DiaryEntry.objects.create(
            user=self.other,
            date=timezone.localdate(),
            content="他人の公開日記",
            visibility=DiaryVisibility.LAB,
        )
        response = self._upload(entry=entry)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(DiaryAttachment.objects.exists())

    def test_delete_removes_attachment(self):
        self._upload()
        attachment = DiaryAttachment.objects.get()
        response = self.client.post(
            reverse("research:diary_attachment_delete", args=[self.entry.pk, attachment.pk])
        )
        self.assertRedirects(response, reverse("research:diary_detail", args=[self.entry.pk]))
        self.assertFalse(DiaryAttachment.objects.exists())

    def test_cannot_delete_other_members_attachment(self):
        entry = DiaryEntry.objects.create(user=self.other, date=timezone.localdate(), content="他人の日記")
        attachment = DiaryAttachment.objects.create(
            diary=entry,
            file=SimpleUploadedFile("x.png", b"data"),
            original_name="x.png",
        )
        response = self.client.post(
            reverse("research:diary_attachment_delete", args=[entry.pk, attachment.pk])
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(DiaryAttachment.objects.filter(pk=attachment.pk).exists())

    def test_deleting_entry_removes_attachments(self):
        self._upload()
        self.client.post(reverse("research:diary_delete", args=[self.entry.pk]))
        self.assertFalse(DiaryAttachment.objects.exists())

    def test_viewer_of_public_entry_sees_attachment_without_delete_button(self):
        entry = DiaryEntry.objects.create(
            user=self.other,
            date=timezone.localdate(),
            content="他人の公開日記",
            visibility=DiaryVisibility.LAB,
        )
        attachment = DiaryAttachment.objects.create(
            diary=entry,
            file=SimpleUploadedFile("shared.png", b"data"),
            original_name="shared.png",
        )
        response = self.client.get(reverse("research:diary_detail", args=[entry.pk]))
        self.assertContains(response, "shared.png")
        self.assertNotContains(
            response, reverse("research:diary_attachment_delete", args=[entry.pk, attachment.pk])
        )

    def test_upload_rejects_get(self):
        response = self.client.get(reverse("research:diary_attachment_create", args=[self.entry.pk]))
        self.assertEqual(response.status_code, 405)
