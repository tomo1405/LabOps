"""優先度1: 研究支援系ビューのテスト（詳細設計書 4章のエンドポイント）。"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from research.models import (
    ConferenceChecklistItem,
    ConferencePrep,
    DiaryEntry,
    DiaryVisibility,
    EventType,
    ScheduleEvent,
)

User = get_user_model()


class LoginRequiredTests(TestCase):
    """未ログインでは全画面がログイン画面へリダイレクトされる。"""

    def test_protected_views_redirect_to_login(self):
        urls = [
            reverse("research:dashboard"),
            reverse("research:diary_list"),
            reverse("research:diary_create"),
            reverse("research:diary_update", args=[1]),
            reverse("research:diary_delete", args=[1]),
            reverse("research:schedule"),
            reverse("research:schedule_event_update", args=[1]),
            reverse("research:schedule_event_delete", args=[1]),
            reverse("research:conference_list"),
            reverse("research:conference_create"),
            reverse("research:conference_update", args=[1]),
            reverse("research:conference_delete", args=[1]),
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


class DiaryViewTests(AuthenticatedTestCase):
    def test_create_diary_assigns_current_user(self):
        response = self.client.post(
            reverse("research:diary_create"),
            {
                "date": "2026-09-04",
                "content": "実験の結果を整理した",
                "tags": "実験",
                "visibility": "private",
            },
        )
        entry = DiaryEntry.objects.get()
        self.assertRedirects(response, reverse("research:diary_detail", args=[entry.pk]))
        self.assertEqual(entry.user, self.user)

    def test_create_diary_rejects_empty_content(self):
        response = self.client.post(
            reverse("research:diary_create"), {"date": "2026-09-04", "content": "", "tags": ""}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DiaryEntry.objects.exists())

    def test_list_shows_only_own_entries(self):
        DiaryEntry.objects.create(user=self.user, date=timezone.localdate(), content="自分の日記")
        DiaryEntry.objects.create(user=self.other, date=timezone.localdate(), content="他人の日記")
        response = self.client.get(reverse("research:diary_list"))
        self.assertContains(response, "自分の日記")
        self.assertNotContains(response, "他人の日記")

    def test_list_filters_by_tag(self):
        DiaryEntry.objects.create(
            user=self.user, date=timezone.localdate(), content="実験の記録", tags="実験"
        )
        DiaryEntry.objects.create(
            user=self.user, date=timezone.localdate(), content="輪読の記録", tags="輪読"
        )
        response = self.client.get(reverse("research:diary_list"), {"tag": "輪読"})
        self.assertContains(response, "輪読の記録")
        self.assertNotContains(response, "実験の記録")

    def test_list_row_keeps_long_content_inside_the_row(self):
        """長い本文で行が横に伸びないよう、flex の子に min-width の指定が入っている。

        指定が外れると text-truncate が効かず、一覧が画面幅を突き破る。
        """
        DiaryEntry.objects.create(user=self.user, date=timezone.localdate(), content="A" * 400, tags="")
        response = self.client.get(reverse("research:diary_list"))
        self.assertContains(response, "diary-row-main")
        self.assertContains(response, "text-truncate")

    def test_detail_of_other_user_entry_returns_404(self):
        entry = DiaryEntry.objects.create(user=self.other, date=timezone.localdate(), content="秘密")
        response = self.client.get(reverse("research:diary_detail", args=[entry.pk]))
        self.assertEqual(response.status_code, 404)


class DiaryVisibilityTests(AuthenticatedTestCase):
    """研究日記の公開範囲（非公開／研究室内に公開）。"""

    def setUp(self):
        super().setUp()
        self.private = DiaryEntry.objects.create(
            user=self.other, date=timezone.localdate(), content="他人の非公開日記"
        )
        self.public = DiaryEntry.objects.create(
            user=self.other,
            date=timezone.localdate(),
            content="他人の公開日記",
            visibility=DiaryVisibility.LAB,
        )

    def test_default_visibility_is_private(self):
        entry = DiaryEntry.objects.create(user=self.user, date=timezone.localdate(), content="自分の日記")
        self.assertEqual(entry.visibility, DiaryVisibility.PRIVATE)
        self.assertFalse(entry.is_public)

    def test_mine_scope_excludes_other_members_public_entries(self):
        DiaryEntry.objects.create(user=self.user, date=timezone.localdate(), content="自分の日記")
        response = self.client.get(reverse("research:diary_list"))
        self.assertContains(response, "自分の日記")
        self.assertNotContains(response, "他人の公開日記")

    def test_lab_scope_shows_only_public_entries(self):
        DiaryEntry.objects.create(
            user=self.user,
            date=timezone.localdate(),
            content="自分の公開日記",
            visibility=DiaryVisibility.LAB,
        )
        DiaryEntry.objects.create(user=self.user, date=timezone.localdate(), content="自分の非公開日記")
        response = self.client.get(reverse("research:diary_list"), {"scope": "lab"})
        self.assertContains(response, "他人の公開日記")
        self.assertContains(response, "自分の公開日記")
        self.assertNotContains(response, "他人の非公開日記")
        self.assertNotContains(response, "自分の非公開日記")

    def test_can_view_other_members_public_entry(self):
        response = self.client.get(reverse("research:diary_detail", args=[self.public.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "他人の公開日記")

    def test_cannot_view_other_members_private_entry(self):
        response = self.client.get(reverse("research:diary_detail", args=[self.private.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cannot_edit_or_delete_other_members_public_entry(self):
        """公開されていても、編集・削除できるのは作成者だけ。"""
        for name in ("research:diary_update", "research:diary_delete"):
            with self.subTest(view=name):
                response = self.client.post(
                    reverse(name, args=[self.public.pk]),
                    {"date": "2026-09-01", "content": "書き換え", "tags": "", "visibility": "lab"},
                )
                self.assertEqual(response.status_code, 404)
        self.assertTrue(DiaryEntry.objects.filter(pk=self.public.pk).exists())

    def test_edit_buttons_hidden_on_other_members_entry(self):
        response = self.client.get(reverse("research:diary_detail", args=[self.public.pk]))
        self.assertNotContains(response, reverse("research:diary_update", args=[self.public.pk]))

    def test_can_publish_own_entry_by_editing(self):
        entry = DiaryEntry.objects.create(user=self.user, date=timezone.localdate(), content="自分の日記")
        self.client.post(
            reverse("research:diary_update", args=[entry.pk]),
            {"date": "2026-09-01", "content": "自分の日記", "tags": "", "visibility": "lab"},
        )
        entry.refresh_from_db()
        self.assertTrue(entry.is_public)


class DiarySearchTests(AuthenticatedTestCase):
    """研究日記のキーワード検索（本文・タグが対象）。"""

    def setUp(self):
        super().setUp()
        DiaryEntry.objects.create(
            user=self.user,
            date=timezone.localdate(),
            content="前処理のバグを修正した。データ件数が想定より少なかった。",
            tags="実装, デバッグ",
        )
        DiaryEntry.objects.create(
            user=self.user,
            date=timezone.localdate() - timedelta(days=1),
            content="関連研究を3本読んだ。評価指標の扱いを整理。",
            tags="論文読み",
        )

    def test_search_matches_content(self):
        response = self.client.get(reverse("research:diary_list"), {"q": "前処理"})
        self.assertContains(response, "前処理のバグ")
        self.assertNotContains(response, "関連研究を3本")

    def test_search_matches_tags(self):
        response = self.client.get(reverse("research:diary_list"), {"q": "論文読み"})
        self.assertContains(response, "関連研究を3本")
        self.assertNotContains(response, "前処理のバグ")

    def test_multiple_words_are_combined_with_and(self):
        response = self.client.get(reverse("research:diary_list"), {"q": "前処理 データ"})
        self.assertEqual(len(response.context["entries"]), 1)

        response = self.client.get(reverse("research:diary_list"), {"q": "前処理 評価指標"})
        self.assertEqual(len(response.context["entries"]), 0)

    def test_search_is_case_insensitive(self):
        DiaryEntry.objects.create(
            user=self.user, date=timezone.localdate(), content="GPUメモリの調整", tags=""
        )
        response = self.client.get(reverse("research:diary_list"), {"q": "gpu"})
        self.assertContains(response, "GPUメモリ")

    def test_search_does_not_cross_visibility_boundary(self):
        """検索しても、他メンバーの非公開日記は出てこない。"""
        DiaryEntry.objects.create(
            user=self.other, date=timezone.localdate(), content="他人の非公開メモ", tags=""
        )
        response = self.client.get(reverse("research:diary_list"), {"q": "メモ"})
        self.assertNotContains(response, "他人の非公開メモ")

        response = self.client.get(reverse("research:diary_list"), {"q": "メモ", "scope": "lab"})
        self.assertNotContains(response, "他人の非公開メモ")

    def test_no_match_shows_message(self):
        response = self.client.get(reverse("research:diary_list"), {"q": "存在しない語"})
        self.assertContains(response, "条件に一致する研究日記はありません")

    def test_excerpt_strips_markdown_syntax(self):
        DiaryEntry.objects.create(
            user=self.user,
            date=timezone.localdate(),
            content="## 見出し\n\n- 箇条書き",
            tags="",
        )
        response = self.client.get(reverse("research:diary_list"))
        self.assertContains(response, "見出し")
        self.assertNotContains(response, "## 見出し")


class DiaryUpdateDeleteTests(AuthenticatedTestCase):
    """研究日記の更新・削除（CRUDのU・D）。"""

    def setUp(self):
        super().setUp()
        self.entry = DiaryEntry.objects.create(
            user=self.user, date=timezone.localdate(), content="修正前の本文", tags="実験"
        )

    def test_edit_form_shows_current_values(self):
        response = self.client.get(reverse("research:diary_update", args=[self.entry.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "修正前の本文")

    def test_update_changes_content_and_keeps_owner(self):
        response = self.client.post(
            reverse("research:diary_update", args=[self.entry.pk]),
            {"date": "2026-09-01", "content": "修正後の本文", "tags": "実験, 解析", "visibility": "private"},
        )
        self.assertRedirects(response, reverse("research:diary_detail", args=[self.entry.pk]))
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.content, "修正後の本文")
        self.assertEqual(self.entry.tag_list(), ["実験", "解析"])
        self.assertEqual(self.entry.user, self.user)

    def test_update_rejects_empty_content(self):
        response = self.client.post(
            reverse("research:diary_update", args=[self.entry.pk]),
            {"date": "2026-09-01", "content": "", "tags": ""},
        )
        self.assertEqual(response.status_code, 200)
        self.entry.refresh_from_db()
        self.assertEqual(self.entry.content, "修正前の本文")

    def test_update_does_not_create_new_entry(self):
        self.client.post(
            reverse("research:diary_update", args=[self.entry.pk]),
            {"date": "2026-09-01", "content": "修正後の本文", "tags": "", "visibility": "private"},
        )
        self.assertEqual(DiaryEntry.objects.count(), 1)

    def test_cannot_edit_other_user_entry(self):
        entry = DiaryEntry.objects.create(user=self.other, date=timezone.localdate(), content="秘密")
        response = self.client.post(
            reverse("research:diary_update", args=[entry.pk]),
            {"date": "2026-09-01", "content": "書き換え", "tags": ""},
        )
        self.assertEqual(response.status_code, 404)
        entry.refresh_from_db()
        self.assertEqual(entry.content, "秘密")

    def test_delete_confirmation_page_does_not_delete(self):
        response = self.client.get(reverse("research:diary_delete", args=[self.entry.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(DiaryEntry.objects.filter(pk=self.entry.pk).exists())

    def test_delete_removes_entry(self):
        response = self.client.post(reverse("research:diary_delete", args=[self.entry.pk]))
        self.assertRedirects(response, reverse("research:diary_list"))
        self.assertFalse(DiaryEntry.objects.filter(pk=self.entry.pk).exists())

    def test_cannot_delete_other_user_entry(self):
        entry = DiaryEntry.objects.create(user=self.other, date=timezone.localdate(), content="秘密")
        response = self.client.post(reverse("research:diary_delete", args=[entry.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(DiaryEntry.objects.filter(pk=entry.pk).exists())


class ScheduleViewTests(AuthenticatedTestCase):
    def test_calendar_shows_own_and_shared_events(self):
        now = timezone.now()
        ScheduleEvent.objects.create(
            user=self.user, title="自分の実験", start_at=now, event_type=EventType.TASK
        )
        ScheduleEvent.objects.create(title="研究室ゼミ", start_at=now, event_type=EventType.TASK)
        ScheduleEvent.objects.create(
            user=self.other, title="他人の予定", start_at=now, event_type=EventType.TASK
        )
        response = self.client.get(reverse("research:schedule"))
        self.assertContains(response, "自分の実験")
        self.assertContains(response, "研究室ゼミ")
        self.assertNotContains(response, "他人の予定")

    def test_calendar_shows_only_requested_month(self):
        target = timezone.localtime(timezone.now()).replace(year=2026, month=5, day=10)
        ScheduleEvent.objects.create(
            user=self.user, title="5月の予定", start_at=target, event_type=EventType.TASK
        )
        response = self.client.get(reverse("research:schedule"), {"year": 2026, "month": 5})
        self.assertContains(response, "5月の予定")
        response = self.client.get(reverse("research:schedule"), {"year": 2026, "month": 6})
        self.assertNotContains(response, "5月の予定")

    def test_invalid_month_returns_404(self):
        for params in ({"year": 2026, "month": 13}, {"year": "abc", "month": 1}):
            with self.subTest(params=params):
                response = self.client.get(reverse("research:schedule"), params)
                self.assertEqual(response.status_code, 404)

    def test_create_event_via_htmx_returns_calendar_partial(self):
        response = self.client.post(
            reverse("research:schedule_event_create"),
            {
                "title": "中間発表",
                "start_at": "2026-09-10T13:00",
                "end_at": "2026-09-10T14:00",
                "event_type": EventType.MILESTONE,
            },
        )
        self.assertEqual(response.status_code, 200)
        event = ScheduleEvent.objects.get()
        self.assertEqual(event.user, self.user)
        self.assertContains(response, "中間発表")

    def test_create_shared_event_has_no_owner(self):
        self.client.post(
            reverse("research:schedule_event_create"),
            {
                "title": "全体ゼミ",
                "start_at": "2026-09-10T13:00",
                "event_type": EventType.TASK,
                "is_shared": "1",
            },
        )
        self.assertIsNone(ScheduleEvent.objects.get().user)

    def test_end_before_start_is_rejected(self):
        response = self.client.post(
            reverse("research:schedule_event_create"),
            {
                "title": "不正な予定",
                "start_at": "2026-09-10T15:00",
                "end_at": "2026-09-10T14:00",
                "event_type": EventType.TASK,
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ScheduleEvent.objects.exists())

    def test_get_is_not_allowed_for_event_endpoint(self):
        response = self.client.get(reverse("research:schedule_event_create"))
        self.assertEqual(response.status_code, 405)


class ScheduleUpdateDeleteTests(AuthenticatedTestCase):
    """研究スケジュールの更新・削除。"""

    def setUp(self):
        super().setUp()
        self.start = timezone.now() + timedelta(days=1)
        self.event = ScheduleEvent.objects.create(
            user=self.user, title="研究ミーティング", start_at=self.start, event_type=EventType.TASK
        )

    def _post_data(self, **overrides):
        data = {
            "title": "研究ミーティング（変更後）",
            "start_at": timezone.localtime(self.start).strftime("%Y-%m-%dT%H:%M"),
            "end_at": "",
            "event_type": EventType.TASK,
            "conference": "",
        }
        data.update(overrides)
        return data

    def test_edit_form_shows_current_values(self):
        response = self.client.get(reverse("research:schedule_event_update", args=[self.event.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "研究ミーティング")

    def test_update_changes_title(self):
        response = self.client.post(
            reverse("research:schedule_event_update", args=[self.event.pk]), self._post_data()
        )
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, "研究ミーティング（変更後）")
        self.assertEqual(ScheduleEvent.objects.count(), 1)

    def test_update_rejects_end_before_start(self):
        response = self.client.post(
            reverse("research:schedule_event_update", args=[self.event.pk]),
            self._post_data(
                end_at=timezone.localtime(self.start - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, "研究ミーティング")

    def test_update_can_switch_to_shared_event(self):
        self.client.post(
            reverse("research:schedule_event_update", args=[self.event.pk]),
            self._post_data(is_shared="1"),
        )
        self.event.refresh_from_db()
        self.assertIsNone(self.event.user)
        self.assertTrue(self.event.is_shared)

    def test_delete_confirmation_page_does_not_delete(self):
        response = self.client.get(reverse("research:schedule_event_delete", args=[self.event.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ScheduleEvent.objects.filter(pk=self.event.pk).exists())

    def test_delete_removes_event(self):
        response = self.client.post(reverse("research:schedule_event_delete", args=[self.event.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ScheduleEvent.objects.filter(pk=self.event.pk).exists())

    def test_cannot_edit_other_members_personal_event(self):
        event = ScheduleEvent.objects.create(
            user=self.other, title="他人の予定", start_at=self.start, event_type=EventType.TASK
        )
        response = self.client.post(
            reverse("research:schedule_event_update", args=[event.pk]), self._post_data()
        )
        self.assertEqual(response.status_code, 404)
        event.refresh_from_db()
        self.assertEqual(event.title, "他人の予定")

    def test_shared_event_can_be_edited_by_any_member(self):
        """研究室共通の予定は誰でも作成できる設計に合わせ、編集も全員に開いている。"""
        event = ScheduleEvent.objects.create(
            user=None, title="研究室全体ゼミ", start_at=self.start, event_type=EventType.TASK
        )
        response = self.client.post(
            reverse("research:schedule_event_update", args=[event.pk]),
            self._post_data(title="研究室全体ゼミ（変更後）", is_shared="1"),
        )
        self.assertEqual(response.status_code, 302)
        event.refresh_from_db()
        self.assertEqual(event.title, "研究室全体ゼミ（変更後）")
        self.assertIsNone(event.user)


class ConferenceViewTests(AuthenticatedTestCase):
    def _prep(self, user=None, days=7) -> ConferencePrep:
        return ConferencePrep.objects.create(
            conference_name="テスト学会",
            deadline=timezone.localdate() + timedelta(days=days),
            user=user or self.user,
        )

    def test_create_prep_with_checklist_lines(self):
        response = self.client.post(
            reverse("research:conference_create"),
            {
                "conference_name": "情報処理学会",
                "deadline": "2026-10-01",
                "checklist_items": "要旨執筆\n\nスライド作成\n",
            },
        )
        self.assertRedirects(response, reverse("research:conference_list"))
        prep = ConferencePrep.objects.get()
        self.assertEqual(prep.user, self.user)
        self.assertEqual(
            list(prep.checklist_items.values_list("item", flat=True)), ["要旨執筆", "スライド作成"]
        )

    def test_list_shows_only_own_preps(self):
        self._prep()
        ConferencePrep.objects.create(
            conference_name="他人の学会", deadline=timezone.localdate(), user=self.other
        )
        response = self.client.get(reverse("research:conference_list"))
        self.assertContains(response, "テスト学会")
        self.assertNotContains(response, "他人の学会")

    def test_near_deadline_is_highlighted(self):
        self._prep(days=3)
        response = self.client.get(reverse("research:conference_list"))
        self.assertContains(response, "bg-warning-subtle")

    def test_toggle_checklist_item(self):
        prep = self._prep()
        item = ConferenceChecklistItem.objects.create(conference=prep, item="要旨執筆")

        response = self.client.post(reverse("research:checklist_item_toggle", args=[prep.pk, item.pk]))
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertTrue(item.done)

        self.client.post(reverse("research:checklist_item_toggle", args=[prep.pk, item.pk]))
        item.refresh_from_db()
        self.assertFalse(item.done)

    def test_toggle_other_user_item_returns_404(self):
        prep = self._prep(user=self.other)
        item = ConferenceChecklistItem.objects.create(conference=prep, item="他人の項目")
        response = self.client.post(reverse("research:checklist_item_toggle", args=[prep.pk, item.pk]))
        self.assertEqual(response.status_code, 404)
        item.refresh_from_db()
        self.assertFalse(item.done)

    def test_toggle_with_mismatched_conference_returns_404(self):
        """他の学会のIDを指定してもチェックを切り替えられない。"""
        prep = self._prep()
        another = self._prep(days=20)
        item = ConferenceChecklistItem.objects.create(conference=prep, item="要旨執筆")
        response = self.client.post(reverse("research:checklist_item_toggle", args=[another.pk, item.pk]))
        self.assertEqual(response.status_code, 404)

    def test_add_checklist_item(self):
        prep = self._prep()
        response = self.client.post(
            reverse("research:checklist_item_create", args=[prep.pk]), {"item": "発表練習"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(prep.checklist_items.count(), 1)
        self.assertContains(response, "発表練習")

    def test_add_empty_checklist_item_is_rejected(self):
        prep = self._prep()
        response = self.client.post(reverse("research:checklist_item_create", args=[prep.pk]), {"item": ""})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(prep.checklist_items.count(), 0)

    def test_add_item_to_other_user_prep_returns_404(self):
        prep = self._prep(user=self.other)
        response = self.client.post(
            reverse("research:checklist_item_create", args=[prep.pk]), {"item": "乗っ取り"}
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(prep.checklist_items.count(), 0)


class ConferenceUpdateDeleteTests(AuthenticatedTestCase):
    """学会準備の更新・削除とチェック項目の削除。"""

    def setUp(self):
        super().setUp()
        self.prep = ConferencePrep.objects.create(
            conference_name="テスト学会",
            deadline=timezone.localdate() + timedelta(days=7),
            user=self.user,
        )
        self.item = ConferenceChecklistItem.objects.create(conference=self.prep, item="要旨執筆")

    def test_edit_form_shows_current_values(self):
        response = self.client.get(reverse("research:conference_update", args=[self.prep.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "テスト学会")

    def test_update_changes_name_and_deadline(self):
        new_deadline = timezone.localdate() + timedelta(days=30)
        response = self.client.post(
            reverse("research:conference_update", args=[self.prep.pk]),
            {
                "conference_name": "テスト学会（変更後）",
                "deadline": new_deadline.isoformat(),
                "checklist_items": "",
            },
        )
        self.assertRedirects(response, reverse("research:conference_list"))
        self.prep.refresh_from_db()
        self.assertEqual(self.prep.conference_name, "テスト学会（変更後）")
        self.assertEqual(self.prep.deadline, new_deadline)
        self.assertEqual(ConferencePrep.objects.count(), 1)

    def test_update_appends_checklist_items_without_removing_existing(self):
        self.client.post(
            reverse("research:conference_update", args=[self.prep.pk]),
            {
                "conference_name": "テスト学会",
                "deadline": self.prep.deadline.isoformat(),
                "checklist_items": "図表作成\nリハーサル",
            },
        )
        self.assertEqual(
            list(self.prep.checklist_items.values_list("item", flat=True)),
            ["要旨執筆", "図表作成", "リハーサル"],
        )

    def test_cannot_edit_other_members_prep(self):
        prep = ConferencePrep.objects.create(
            conference_name="他人の学会", deadline=timezone.localdate(), user=self.other
        )
        response = self.client.post(
            reverse("research:conference_update", args=[prep.pk]),
            {"conference_name": "書き換え", "deadline": "2026-12-01", "checklist_items": ""},
        )
        self.assertEqual(response.status_code, 404)
        prep.refresh_from_db()
        self.assertEqual(prep.conference_name, "他人の学会")

    def test_delete_confirmation_page_does_not_delete(self):
        response = self.client.get(reverse("research:conference_delete", args=[self.prep.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(ConferencePrep.objects.filter(pk=self.prep.pk).exists())

    def test_delete_removes_prep_and_checklist_items(self):
        response = self.client.post(reverse("research:conference_delete", args=[self.prep.pk]))
        self.assertRedirects(response, reverse("research:conference_list"))
        self.assertFalse(ConferencePrep.objects.filter(pk=self.prep.pk).exists())
        self.assertFalse(ConferenceChecklistItem.objects.filter(pk=self.item.pk).exists())

    def test_delete_keeps_linked_schedule_event(self):
        """紐付けた予定は残り、学会への紐付けだけが解除される。"""
        event = ScheduleEvent.objects.create(
            user=self.user,
            title="原稿を仕上げる",
            start_at=timezone.now() + timedelta(days=1),
            event_type=EventType.TASK,
            conference=self.prep,
        )
        self.client.post(reverse("research:conference_delete", args=[self.prep.pk]))
        event.refresh_from_db()
        self.assertIsNone(event.conference)

    def test_delete_checklist_item(self):
        response = self.client.post(
            reverse("research:checklist_item_delete", args=[self.prep.pk, self.item.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(ConferenceChecklistItem.objects.filter(pk=self.item.pk).exists())

    def test_cannot_delete_other_members_checklist_item(self):
        prep = ConferencePrep.objects.create(
            conference_name="他人の学会", deadline=timezone.localdate(), user=self.other
        )
        item = ConferenceChecklistItem.objects.create(conference=prep, item="他人の項目")
        response = self.client.post(reverse("research:checklist_item_delete", args=[prep.pk, item.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(ConferenceChecklistItem.objects.filter(pk=item.pk).exists())


class DashboardViewTests(AuthenticatedTestCase):
    def test_diary_preview_strips_markdown_syntax(self):
        DiaryEntry.objects.create(
            user=self.user,
            date=timezone.localdate(),
            content="## 今日の実験\n\n- 前処理を修正",
        )
        response = self.client.get(reverse("research:dashboard"))
        self.assertContains(response, "今日の実験")
        self.assertNotContains(response, "## 今日の実験")

    def test_dashboard_lists_own_data_only(self):
        DiaryEntry.objects.create(user=self.user, date=timezone.localdate(), content="自分の記録")
        DiaryEntry.objects.create(user=self.other, date=timezone.localdate(), content="他人の記録")
        ScheduleEvent.objects.create(
            user=self.user,
            title="来週の実験",
            start_at=timezone.now() + timedelta(days=7),
            event_type=EventType.TASK,
        )
        ConferencePrep.objects.create(
            conference_name="近い学会", deadline=timezone.localdate() + timedelta(days=2), user=self.user
        )

        response = self.client.get(reverse("research:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "自分の記録")
        self.assertNotContains(response, "他人の記録")
        self.assertContains(response, "来週の実験")
        self.assertContains(response, "近い学会")

    def test_dashboard_excludes_past_events(self):
        ScheduleEvent.objects.create(
            user=self.user,
            title="終わった予定",
            start_at=timezone.now() - timedelta(days=1),
            event_type=EventType.TASK,
        )
        response = self.client.get(reverse("research:dashboard"))
        self.assertNotContains(response, "終わった予定")
