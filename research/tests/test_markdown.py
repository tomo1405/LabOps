"""研究日記のMarkdown描画とサニタイズのテスト。"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from research.markdown_render import render_markdown
from research.models import DiaryEntry

User = get_user_model()


class MarkdownRenderTests(TestCase):
    def test_headings_and_lists(self):
        html = render_markdown("## 実験メモ\n\n- 学習率 1e-4\n- バッチサイズ 32")
        self.assertIn("<h2>実験メモ</h2>", html)
        self.assertIn("<li>学習率 1e-4</li>", html)

    def test_emphasis_and_inline_code(self):
        html = render_markdown("**重要** な `parameter` を変えた")
        self.assertIn("<strong>重要</strong>", html)
        self.assertIn("<code>parameter</code>", html)

    def test_code_block(self):
        html = render_markdown("```\nprint('hello')\n```")
        self.assertIn("<pre>", html)
        self.assertIn("print(", html)

    def test_table(self):
        html = render_markdown("| 条件 | 精度 |\n|---|---|\n| A | 0.91 |")
        self.assertIn("<table>", html)
        self.assertIn("<td>0.91</td>", html)

    def test_single_newline_becomes_line_break(self):
        """研究メモは1行改行で書かれることが多いため、そのまま改行として扱う。"""
        html = render_markdown("1行目\n2行目")
        self.assertIn("<br", html)

    def test_script_tag_is_removed(self):
        html = render_markdown("メモ<script>alert('xss')</script>")
        self.assertNotIn("<script>", html)
        self.assertNotIn("alert(", html)

    def test_event_handler_attribute_is_removed(self):
        html = render_markdown('<img src="x" onerror="alert(1)">')
        self.assertNotIn("onerror", html)

    def test_javascript_url_is_removed(self):
        html = render_markdown("[クリック](javascript:alert(1))")
        self.assertNotIn("javascript:", html)

    def test_iframe_is_removed(self):
        html = render_markdown('<iframe src="https://example.com"></iframe>')
        self.assertNotIn("<iframe", html)

    def test_external_link_gets_noopener(self):
        html = render_markdown("[参考](https://example.com)")
        self.assertIn('href="https://example.com"', html)
        self.assertIn("noopener", html)

    def test_empty_content_renders_empty(self):
        self.assertEqual(render_markdown(""), "")


class DiaryMarkdownViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")

    def setUp(self):
        self.client.force_login(self.user)

    def test_detail_renders_markdown(self):
        entry = DiaryEntry.objects.create(
            user=self.user,
            date=timezone.localdate(),
            content="## 今日の実験\n\n- 前処理を修正",
        )
        response = self.client.get(reverse("research:diary_detail", args=[entry.pk]))
        self.assertContains(response, "<h2>今日の実験</h2>", html=False)
        self.assertContains(response, "<li>前処理を修正</li>", html=False)

    def test_detail_does_not_render_script(self):
        entry = DiaryEntry.objects.create(
            user=self.user,
            date=timezone.localdate(),
            content="<script>alert('xss')</script>",
        )
        response = self.client.get(reverse("research:diary_detail", args=[entry.pk]))
        self.assertNotContains(response, "<script>alert", html=False)

    def test_stored_content_keeps_original_markdown(self):
        """保存されるのは入力したMarkdownそのもので、HTMLではない。"""
        self.client.post(
            reverse("research:diary_create"),
            {
                "date": "2026-09-04",
                "content": "## 見出し",
                "tags": "",
                "visibility": "private",
            },
        )
        self.assertEqual(DiaryEntry.objects.get().content, "## 見出し")
