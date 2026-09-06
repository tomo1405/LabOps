"""学会準備支援機能のテスト（コードレビュー REV-CONF-001〜003 に対応）。"""

from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import DatabaseError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from research.forms import ConferencePrepForm
from research.models import ConferenceChecklistItem, ConferencePrep

User = get_user_model()

ITEM_MAX_LENGTH = ConferencePrepForm.ITEM_MAX_LENGTH


class ConferenceTestCase(TestCase):
    """学会準備テストの共通土台。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")

    def setUp(self):
        self.client.force_login(self.user)
        self.prep = ConferencePrep.objects.create(
            conference_name="テスト学会",
            deadline=timezone.localdate() + timedelta(days=7),
            user=self.user,
        )


class ConferenceChecklistLengthTests(ConferenceTestCase):
    """REV-CONF-001: 一括入力の項目にもモデルと同じ長さ制約を適用する。"""

    def _create(self, checklist_items):
        return self.client.post(
            reverse("research:conference_create"),
            {
                "conference_name": "情報処理学会",
                "deadline": "2026-10-01",
                "checklist_items": checklist_items,
            },
        )

    def _update(self, checklist_items):
        return self.client.post(
            reverse("research:conference_update", args=[self.prep.pk]),
            {
                "conference_name": "改名した学会",
                "deadline": "2026-11-01",
                "checklist_items": checklist_items,
            },
        )

    def _too_long_error(self, lines):
        return f"{lines}が長すぎます。1項目は{ITEM_MAX_LENGTH}文字以内にしてください。"

    def test_create_accepts_item_at_max_length(self):
        response = self._create("あ" * ITEM_MAX_LENGTH)
        self.assertRedirects(response, reverse("research:conference_list"))
        created = ConferencePrep.objects.get(conference_name="情報処理学会")
        self.assertEqual(created.checklist_items.count(), 1)

    def test_create_rejects_item_over_max_length(self):
        response = self._create("あ" * (ITEM_MAX_LENGTH + 1))
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "checklist_items", self._too_long_error("1行目"))

    def test_create_error_names_every_offending_line(self):
        over = "あ" * (ITEM_MAX_LENGTH + 1)
        response = self._create(f"短い項目\n{over}\n{over}")
        self.assertFormError(
            response.context["form"], "checklist_items", self._too_long_error("2行目、3行目")
        )

    def test_create_does_not_save_the_prep_when_items_are_invalid(self):
        """項目が不正なら、学会準備本体も作られない（部分保存しない）。"""
        self._create("あ" * (ITEM_MAX_LENGTH + 1))
        self.assertFalse(ConferencePrep.objects.filter(conference_name="情報処理学会").exists())

    def test_update_accepts_item_at_max_length(self):
        response = self._update("あ" * ITEM_MAX_LENGTH)
        self.assertRedirects(response, reverse("research:conference_list"))
        self.assertEqual(self.prep.checklist_items.count(), 1)

    def test_update_rejects_item_over_max_length(self):
        response = self._update("あ" * (ITEM_MAX_LENGTH + 1))
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "checklist_items", self._too_long_error("1行目"))

    def test_update_keeps_original_values_when_items_are_invalid(self):
        """項目が不正なら、学会名・締切日の変更も反映されない。"""
        self._update("あ" * (ITEM_MAX_LENGTH + 1))
        self.prep.refresh_from_db()
        self.assertEqual(self.prep.conference_name, "テスト学会")
        self.assertEqual(self.prep.checklist_items.count(), 0)

    def test_individual_add_still_rejects_item_over_max_length(self):
        response = self.client.post(
            reverse("research:checklist_item_create", args=[self.prep.pk]),
            {"item": "あ" * (ITEM_MAX_LENGTH + 1)},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.prep.checklist_items.count(), 0)

    def test_create_rolls_back_the_prep_when_bulk_create_fails(self):
        """項目の一括作成がDBエラーになったら、学会準備本体もロールバックされる。"""
        with mock.patch.object(
            ConferenceChecklistItem.objects, "bulk_create", side_effect=DatabaseError("boom")
        ):
            with self.assertRaises(DatabaseError):
                self._create("要旨執筆")
        self.assertFalse(ConferencePrep.objects.filter(conference_name="情報処理学会").exists())

    def test_update_rolls_back_the_prep_when_bulk_create_fails(self):
        with mock.patch.object(
            ConferenceChecklistItem.objects, "bulk_create", side_effect=DatabaseError("boom")
        ):
            with self.assertRaises(DatabaseError):
                self._update("要旨執筆")
        self.prep.refresh_from_db()
        self.assertEqual(self.prep.conference_name, "テスト学会")


class ConferenceProgressDisplayTests(ConferenceTestCase):
    """REV-CONF-002: 一覧に完了率と進捗バーを表示し、htmx操作後も更新する。"""

    def _items(self, count, done=0):
        return [
            ConferenceChecklistItem.objects.create(conference=self.prep, item=f"項目{i}", done=i < done)
            for i in range(count)
        ]

    def test_list_shows_progress_bar(self):
        self._items(4, done=1)
        response = self.client.get(reverse("research:conference_list"))
        self.assertContains(response, f'id="conference-progress-{self.prep.pk}"')
        self.assertContains(response, 'aria-valuenow="25"')
        self.assertContains(response, "完了 25%")

    def test_list_shows_zero_percent_without_items(self):
        response = self.client.get(reverse("research:conference_list"))
        self.assertContains(response, 'aria-valuenow="0"')
        self.assertContains(response, "完了 0%")

    def test_toggle_updates_progress_out_of_band(self):
        items = self._items(2)
        response = self.client.post(
            reverse("research:checklist_item_toggle", args=[self.prep.pk, items[0].pk])
        )
        self.assertContains(response, 'hx-swap-oob="true"')
        self.assertContains(response, f'id="conference-progress-{self.prep.pk}"')
        self.assertContains(response, 'aria-valuenow="50"')

    def test_adding_item_updates_progress(self):
        self._items(1, done=1)
        response = self.client.post(
            reverse("research:checklist_item_create", args=[self.prep.pk]), {"item": "発表練習"}
        )
        # 完了1件 / 全2件 = 50%
        self.assertContains(response, 'aria-valuenow="50"')

    def test_deleting_item_updates_progress(self):
        items = self._items(2, done=1)
        response = self.client.post(
            reverse("research:checklist_item_delete", args=[self.prep.pk, items[1].pk])
        )
        # 残った1件がすべて完了しているので100%
        self.assertContains(response, 'aria-valuenow="100"')


class ChecklistHtmxErrorDisplayTests(ConferenceTestCase):
    """REV-CONF-003: htmxの入力エラーが画面で確認できること。"""

    def test_error_response_contains_field_error(self):
        response = self.client.post(
            reverse("research:checklist_item_create", args=[self.prep.pk]), {"item": ""}
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "このフィールドは必須です。", status_code=400)

    def test_error_response_keeps_the_entered_value(self):
        too_long = "あ" * (ITEM_MAX_LENGTH + 1)
        response = self.client.post(
            reverse("research:checklist_item_create", args=[self.prep.pk]), {"item": too_long}
        )
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, too_long, status_code=400)

    def test_invalid_item_is_not_saved(self):
        self.client.post(reverse("research:checklist_item_create", args=[self.prep.pk]), {"item": ""})
        self.assertEqual(self.prep.checklist_items.count(), 0)

    def test_pages_load_the_handler_that_swaps_400_responses(self):
        response = self.client.get(reverse("research:conference_list"))
        self.assertContains(response, "js/app.js")

    def test_handler_swaps_only_400_responses(self):
        source = (settings.BASE_DIR / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("htmx:beforeSwap", source)
        self.assertIn("shouldSwap", source)
        self.assertIn("400", source)
