"""研究日記の添付ファイルのテスト。"""

import shutil
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from research.models import DiaryAttachment, DiaryComment, DiaryEntry, DiaryVisibility

User = get_user_model()

MEDIA_ROOT = tempfile.mkdtemp(prefix="labops-test-media-")

# 形式検証（REV-002）を通るように、拡張子と整合する中身を用意する
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n"
CSV_BYTES = b"date,value\n2026-09-05,1\n"
ZIP_BYTES = b"PK\x03\x04" + b"\x00" * 32


@override_settings(MEDIA_ROOT=MEDIA_ROOT)
class DiaryAttachmentTestCase(TestCase):
    """添付テストの共通土台。"""

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

    def _upload(self, name="graph.png", content=PNG_BYTES, entry=None, content_type=None):
        upload = SimpleUploadedFile(name, content, content_type=content_type)
        return self.client.post(
            reverse("research:diary_attachment_create", args=[(entry or self.entry).pk]),
            {"file": upload},
        )

    def _attach(self, entry, name="shared.png", content=PNG_BYTES):
        """フォームを通さずに添付を作る（配信・削除の検証用）。"""
        return DiaryAttachment.objects.create(
            diary=entry, file=SimpleUploadedFile(name, content), original_name=name
        )

    def _stored_path(self, attachment: DiaryAttachment) -> Path:
        return Path(MEDIA_ROOT) / attachment.file.name


class DiaryAttachmentUploadTests(DiaryAttachmentTestCase):
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
        self._upload(name="notes.pdf", content=PDF_BYTES)
        self.assertFalse(DiaryAttachment.objects.get().is_image)

    def test_multiple_attachments_per_entry(self):
        self._upload(name="a.png")
        self._upload(name="b.csv", content=CSV_BYTES)
        self.assertEqual(self.entry.attachments.count(), 2)

    def test_oversized_file_is_rejected(self):
        oversized = PNG_BYTES + b"x" * (10 * 1024 * 1024)
        response = self._upload(name="big.png", content=oversized)
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
        attachment = self._attach(entry, name="x.png")
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
        attachment = self._attach(entry)
        response = self.client.get(reverse("research:diary_detail", args=[entry.pk]))
        self.assertContains(response, "shared.png")
        self.assertNotContains(
            response, reverse("research:diary_attachment_delete", args=[entry.pk, attachment.pk])
        )

    def test_upload_rejects_get(self):
        response = self.client.get(reverse("research:diary_attachment_create", args=[self.entry.pk]))
        self.assertEqual(response.status_code, 405)


class DiaryAttachmentFormatTests(DiaryAttachmentTestCase):
    """REV-002: 能動的コンテンツを受け付けないこと。"""

    def test_html_upload_is_rejected(self):
        response = self._upload(name="evil.html", content=b"<script>alert(1)</script>")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DiaryAttachment.objects.exists())

    def test_svg_upload_is_rejected(self):
        response = self._upload(name="evil.svg", content=b"<svg xmlns='http://www.w3.org/2000/svg'/>")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DiaryAttachment.objects.exists())

    def test_javascript_upload_is_rejected(self):
        response = self._upload(name="evil.js", content=b"alert(1)")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DiaryAttachment.objects.exists())

    def test_allowed_formats_are_accepted(self):
        for name, content in (
            ("figure.png", PNG_BYTES),
            ("photo.jpg", JPEG_BYTES),
            ("paper.pdf", PDF_BYTES),
            ("result.csv", CSV_BYTES),
            ("slides.pptx", ZIP_BYTES),
        ):
            with self.subTest(name=name):
                response = self._upload(name=name, content=content)
                self.assertRedirects(response, reverse("research:diary_detail", args=[self.entry.pk]))
        self.assertEqual(self.entry.attachments.count(), 5)

    def test_client_content_type_alone_does_not_decide_format(self):
        """image/png を申告したHTMLでも、拡張子と中身で拒否される。"""
        response = self._upload(
            name="evil.html", content=b"<script>alert(1)</script>", content_type="image/png"
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DiaryAttachment.objects.exists())

    def test_extension_must_match_file_signature(self):
        """拡張子を .png に偽装したHTMLは拒否される。"""
        response = self._upload(name="evil.png", content=b"<html><script>alert(1)</script></html>")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(DiaryAttachment.objects.exists())

    def test_rejection_shows_reason_on_the_detail_page(self):
        response = self._upload(name="evil.svg", content=b"<svg/>")
        self.assertContains(response, "添付できません", status_code=400)


class DiaryAttachmentDownloadTests(DiaryAttachmentTestCase):
    """REV-001: 添付は認可付きビュー経由でのみ取得できること。"""

    def setUp(self):
        super().setUp()
        self.private_attachment = self._attach(self.entry, name="private.png")
        self.public_entry = DiaryEntry.objects.create(
            user=self.other,
            date=timezone.localdate(),
            content="他人の公開日記",
            visibility=DiaryVisibility.LAB,
        )
        self.public_attachment = self._attach(self.public_entry, name="public.png")
        self.other_private_entry = DiaryEntry.objects.create(
            user=self.other, date=timezone.localdate(), content="他人の非公開日記"
        )
        self.other_private_attachment = self._attach(self.other_private_entry, name="secret.png")

    def _download(self, attachment, diary_pk=None):
        return self.client.get(
            reverse(
                "research:diary_attachment_download",
                args=[diary_pk or attachment.diary_id, attachment.pk],
            )
        )

    def test_owner_can_download_own_private_attachment(self):
        response = self._download(self.private_attachment)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), PNG_BYTES)

    def test_anonymous_user_cannot_download_private_attachment(self):
        self.client.logout()
        response = self._download(self.private_attachment)
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response["Location"])

    def test_other_member_cannot_download_private_attachment(self):
        response = self._download(self.other_private_attachment)
        self.assertEqual(response.status_code, 404)

    def test_other_member_can_download_public_attachment(self):
        response = self._download(self.public_attachment)
        self.assertEqual(response.status_code, 200)

    def test_mismatched_diary_and_attachment_returns_404(self):
        response = self._download(self.public_attachment, diary_pk=self.entry.pk)
        self.assertEqual(response.status_code, 404)

    def test_media_url_is_not_routed(self):
        """/media/ 配下は Django からも配信しない（直接参照を残さない）。"""
        response = self.client.get("/media/" + self.private_attachment.file.name)
        self.assertEqual(response.status_code, 404)

    def test_detail_page_links_to_authorized_url(self):
        response = self.client.get(reverse("research:diary_detail", args=[self.entry.pk]))
        self.assertContains(response, self.private_attachment.download_url)
        self.assertNotContains(response, "/media/")

    def test_image_is_served_inline_with_nosniff(self):
        response = self._download(self.private_attachment)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("inline", response["Content-Disposition"])

    def test_non_image_is_forced_to_download(self):
        attachment = self._attach(self.entry, name="notes.pdf", content=PDF_BYTES)
        response = self._download(attachment)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertIn("attachment", response["Content-Disposition"])

    def test_content_type_comes_from_the_extension(self):
        attachment = self._attach(self.entry, name="result.csv", content=CSV_BYTES)
        response = self._download(attachment)
        self.assertEqual(response["Content-Type"], "text/csv")

    def test_download_rejects_post(self):
        response = self.client.post(
            reverse(
                "research:diary_attachment_download",
                args=[self.entry.pk, self.private_attachment.pk],
            )
        )
        self.assertEqual(response.status_code, 405)

    @override_settings(USE_X_ACCEL_REDIRECT=True)
    def test_x_accel_redirect_delegates_body_to_nginx(self):
        response = self._download(self.private_attachment)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Accel-Redirect"], "/media/" + self.private_attachment.file.name)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.content, b"")

    @override_settings(USE_X_ACCEL_REDIRECT=True)
    def test_x_accel_redirect_still_checks_permission(self):
        response = self._download(self.other_private_attachment)
        self.assertEqual(response.status_code, 404)


class DiaryAttachmentFileLifecycleTests(DiaryAttachmentTestCase):
    """REV-003: レコードの削除に合わせて実体も消えること。"""

    def test_deleting_attachment_removes_stored_file(self):
        attachment = self._attach(self.entry)
        path = self._stored_path(attachment)
        self.assertTrue(path.exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("research:diary_attachment_delete", args=[self.entry.pk, attachment.pk]))
        self.assertFalse(path.exists())

    def test_deleting_entry_removes_stored_files(self):
        first = self._attach(self.entry, name="one.png")
        second = self._attach(self.entry, name="two.csv", content=CSV_BYTES)
        paths = [self._stored_path(first), self._stored_path(second)]
        self.assertTrue(all(p.exists() for p in paths))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("research:diary_delete", args=[self.entry.pk]))
        self.assertFalse(DiaryAttachment.objects.exists())
        for path in paths:
            with self.subTest(path=path.name):
                self.assertFalse(path.exists())

    def test_deleting_user_removes_stored_files(self):
        attachment = self._attach(self.entry)
        path = self._stored_path(attachment)
        with self.captureOnCommitCallbacks(execute=True):
            User.objects.filter(pk=self.user.pk).delete()
        self.assertFalse(DiaryAttachment.objects.exists())
        self.assertFalse(path.exists())

    def test_queryset_bulk_delete_removes_stored_files(self):
        attachment = self._attach(self.entry)
        path = self._stored_path(attachment)
        with self.captureOnCommitCallbacks(execute=True):
            DiaryAttachment.objects.all().delete()
        self.assertFalse(path.exists())


class DiaryAttachmentErrorRenderingTests(DiaryAttachmentTestCase):
    """REV-004: 添付エラー後も詳細画面の構成が変わらないこと。"""

    def test_comment_form_is_still_shown_after_oversized_upload(self):
        oversized = PNG_BYTES + b"x" * (10 * 1024 * 1024)
        response = self._upload(name="big.png", content=oversized)
        self.assertEqual(response.status_code, 400)
        self.assertIsNotNone(response.context["comment_form"])
        self.assertContains(
            response,
            reverse("research:diary_comment_create", args=[self.entry.pk]),
            status_code=400,
        )

    def test_error_and_existing_comments_are_shown_together(self):
        DiaryComment.objects.create(diary=self.entry, author=self.other, body="既存のコメント")
        response = self._upload(name="evil.svg", content=b"<svg/>")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "添付できません", status_code=400)
        self.assertContains(response, "既存のコメント", status_code=400)
