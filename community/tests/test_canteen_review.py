"""学食メニュー共有機能のテスト（コードレビュー REV-CAN-001〜002 に対応）。"""

from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import DatabaseError, IntegrityError
from django.db.models import QuerySet
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from community import canteen as canteen_service
from community.forms import CanteenMenuForm
from community.models import CanteenMenu, CanteenMenuItem, MenuCategory

User = get_user_model()

ITEM_MAX_LENGTH = CanteenMenuForm.ITEM_MAX_LENGTH
MAX_ITEMS = CanteenMenuForm.MAX_ITEMS


class CanteenTestCase(TestCase):
    """学食メニューテストの共通土台。"""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")
        cls.other = User.objects.create_user(email="other@example.com", password="pw12345!", name="他人")

    def setUp(self):
        self.client.force_login(self.user)
        self.today = timezone.localdate()

    def _post_create(self, **overrides):
        data = {
            "date": self.today.isoformat(),
            "set_meals": "からあげ定食",
            "donburi": "親子丼",
            "menu_text": "",
        }
        data.update(overrides)
        return self.client.post(reverse("community:canteen_create"), data)

    def _post_update(self, menu, **overrides):
        data = {
            "date": menu.date.isoformat(),
            "set_meals": "からあげ定食",
            "donburi": "親子丼",
            "menu_text": "",
        }
        data.update(overrides)
        return self.client.post(reverse("community:canteen_update", args=[menu.pk]), data)

    def _names(self, menu, category=MenuCategory.SET_MEAL):
        return [item.name for item in menu.items_of(category)]


class CanteenSaveAtomicityTests(CanteenTestCase):
    """REV-CAN-001: 本体と品目の置換を原子的・排他的に行う。"""

    def _existing_menu(self, day=None, set_meals=("既存の定食",), menu_text="既存の補足"):
        menu = CanteenMenu.objects.create(
            date=day or self.today, menu_text=menu_text, registered_by=self.other
        )
        CanteenMenuItem.objects.bulk_create(
            [
                CanteenMenuItem(menu=menu, category=MenuCategory.SET_MEAL, name=name, position=i)
                for i, name in enumerate(set_meals)
            ]
        )
        return menu

    def test_save_runs_inside_a_transaction(self):
        seen = {}

        def record(*args, **kwargs):
            from django.db import transaction

            seen["in_atomic_block"] = transaction.get_connection().in_atomic_block
            return mock.DEFAULT

        with mock.patch.object(
            CanteenMenuItem.objects,
            "bulk_create",
            side_effect=record,
            wraps=CanteenMenuItem.objects.bulk_create,
        ):
            self._post_create()
        self.assertTrue(seen["in_atomic_block"])

    def test_target_date_is_locked_before_it_is_read(self):
        original = QuerySet.select_for_update
        with mock.patch.object(QuerySet, "select_for_update", autospec=True, side_effect=original) as locked:
            self._post_create()
        self.assertTrue(locked.called)

    def test_item_failure_rolls_back_the_menu_and_existing_items(self):
        """品目の挿入に失敗したら、本体・登録者・既存品目のすべてが元に戻る。"""
        menu = self._existing_menu()
        with (
            mock.patch.object(CanteenMenuItem.objects, "bulk_create", side_effect=DatabaseError("boom")),
            self.assertRaises(DatabaseError),
        ):
            self._post_create(set_meals="新しい定食", menu_text="新しい補足")
        menu.refresh_from_db()
        self.assertEqual(menu.menu_text, "既存の補足")
        self.assertEqual(menu.registered_by, self.other)
        self.assertEqual(self._names(menu), ["既存の定食"])

    def test_item_failure_keeps_the_menu_that_would_be_replaced(self):
        """日付を移す編集が失敗しても、置換先のメニューは消えない。"""
        source = self._existing_menu(day=self.today - timedelta(days=1), set_meals=("移動元",))
        target = self._existing_menu(day=self.today, set_meals=("置換先",))
        with (
            mock.patch.object(CanteenMenuItem.objects, "bulk_create", side_effect=DatabaseError("boom")),
            self.assertRaises(DatabaseError),
        ):
            self._post_update(source, date=self.today.isoformat(), set_meals="移動後")
        self.assertTrue(CanteenMenu.objects.filter(pk=target.pk).exists())
        target.refresh_from_db()
        self.assertEqual(self._names(target), ["置換先"])
        source.refresh_from_db()
        self.assertEqual(source.date, self.today - timedelta(days=1))
        self.assertEqual(self._names(source), ["移動元"])

    def test_re_registering_replaces_items_without_mixing(self):
        """同じ日への再登録では、最後の入力の品目だけが残る。"""
        self._post_create(set_meals="A定食\nB定食", donburi="A丼")
        self._post_create(set_meals="C定食", donburi="B丼\nC丼")
        menu = CanteenMenu.objects.get(date=self.today)
        self.assertEqual(self._names(menu), ["C定食"])
        self.assertEqual(self._names(menu, MenuCategory.DONBURI), ["B丼", "C丼"])
        self.assertEqual(CanteenMenuItem.objects.count(), 3)

    def test_concurrent_creation_falls_back_to_overwriting(self):
        """同時作成で一意制約に触れた場合は、先に作られた登録を上書きする。"""
        existing = CanteenMenu.objects.create(date=self.today, menu_text="先に作られた登録")
        with mock.patch.object(CanteenMenu.objects, "create", side_effect=IntegrityError("duplicate key")):
            self._post_create(set_meals="あとから登録", menu_text="あとからの補足")
        self.assertEqual(CanteenMenu.objects.filter(date=self.today).count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.menu_text, "あとからの補足")
        self.assertEqual(self._names(existing), ["あとから登録"])

    def test_moving_two_menus_to_the_same_date_keeps_one_record(self):
        """異なるメニューを同じ日へ移しても、その日の登録は1件に収まる。"""
        first = self._existing_menu(day=self.today - timedelta(days=2), set_meals=("1件目",))
        second = self._existing_menu(day=self.today - timedelta(days=1), set_meals=("2件目",))
        self._post_update(first, date=self.today.isoformat(), set_meals="1件目")
        self._post_update(second, date=self.today.isoformat(), set_meals="2件目")
        self.assertEqual(CanteenMenu.objects.filter(date=self.today).count(), 1)
        menu = CanteenMenu.objects.get(date=self.today)
        self.assertEqual(self._names(menu), ["2件目"])

    def test_successful_save_updates_the_registrar(self):
        menu = self._existing_menu()
        self._post_create(set_meals="新しい定食")
        menu.refresh_from_db()
        self.assertEqual(menu.registered_by, self.user)
        self.assertEqual(self._names(menu), ["新しい定食"])


class CanteenItemLengthTests(CanteenTestCase):
    """REV-CAN-002: 品名の長さをフォーム段階で検証する。"""

    def _too_long_error(self, lines):
        return f"{lines}が長すぎます。1品は{ITEM_MAX_LENGTH}文字以内にしてください。"

    def test_form_accepts_name_at_max_length(self):
        response = self._post_create(set_meals="あ" * ITEM_MAX_LENGTH)
        self.assertRedirects(response, reverse("community:canteen_today"))
        menu = CanteenMenu.objects.get(date=self.today)
        self.assertEqual(self._names(menu), ["あ" * ITEM_MAX_LENGTH])

    def test_form_rejects_set_meal_over_max_length(self):
        response = self._post_create(set_meals="あ" * (ITEM_MAX_LENGTH + 1))
        self.assertEqual(response.status_code, 400)
        self.assertFormError(response.context["form"], "set_meals", self._too_long_error("1行目"))
        self.assertFalse(CanteenMenu.objects.exists())

    def test_form_rejects_donburi_over_max_length(self):
        response = self._post_create(donburi="あ" * (ITEM_MAX_LENGTH + 1))
        self.assertEqual(response.status_code, 400)
        self.assertFormError(response.context["form"], "donburi", self._too_long_error("1行目"))
        self.assertFalse(CanteenMenu.objects.exists())

    def test_error_names_only_the_offending_lines(self):
        over = "あ" * (ITEM_MAX_LENGTH + 1)
        response = self._post_create(set_meals=f"短い定食\n{over}\n{over}")
        self.assertFormError(response.context["form"], "set_meals", self._too_long_error("2行目、3行目"))

    def test_existing_menu_is_untouched_when_one_line_is_too_long(self):
        menu = CanteenMenu.objects.create(date=self.today, menu_text="既存の補足", registered_by=self.other)
        CanteenMenuItem.objects.create(
            menu=menu, category=MenuCategory.SET_MEAL, name="既存の定食", position=0
        )
        response = self._post_create(
            set_meals="短い定食\n" + "あ" * (ITEM_MAX_LENGTH + 1), menu_text="新しい補足"
        )
        self.assertEqual(response.status_code, 400)
        menu.refresh_from_db()
        self.assertEqual(menu.menu_text, "既存の補足")
        self.assertEqual(menu.registered_by, self.other)
        self.assertEqual(self._names(menu), ["既存の定食"])

    def test_edit_screen_applies_the_same_limit(self):
        menu = CanteenMenu.objects.create(date=self.today, menu_text="補足")
        response = self._post_update(menu, set_meals="あ" * (ITEM_MAX_LENGTH + 1))
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context["form"], "set_meals", self._too_long_error("1行目"))

    def test_too_many_items_are_rejected(self):
        response = self._post_create(set_meals="\n".join(f"定食{i}" for i in range(MAX_ITEMS + 1)))
        self.assertEqual(response.status_code, 400)
        self.assertFormError(
            response.context["form"],
            "set_meals",
            f"品目が多すぎます。1区分{MAX_ITEMS}品までにしてください。",
        )

    def test_item_count_at_the_limit_is_accepted(self):
        response = self._post_create(set_meals="\n".join(f"定食{i}" for i in range(MAX_ITEMS)), donburi="")
        self.assertRedirects(response, reverse("community:canteen_today"))
        menu = CanteenMenu.objects.get(date=self.today)
        self.assertEqual(len(self._names(menu)), MAX_ITEMS)

    def test_length_error_does_not_add_the_empty_input_error(self):
        """品名エラーのときに「いずれかを入力してください」を重ねない。"""
        response = self._post_create(set_meals="あ" * (ITEM_MAX_LENGTH + 1), donburi="", menu_text="")
        form = response.context["form"]
        self.assertIn("set_meals", form.errors)
        self.assertNotIn("__all__", form.errors)

    def test_blank_lines_are_still_removed(self):
        response = self._post_create(set_meals="からあげ定食\n\n  \n鯖の味噌煮定食")
        self.assertRedirects(response, reverse("community:canteen_today"))
        menu = CanteenMenu.objects.get(date=self.today)
        self.assertEqual(self._names(menu), ["からあげ定食", "鯖の味噌煮定食"])

    def test_service_receives_only_validated_names(self):
        form = CanteenMenuForm(
            {
                "date": self.today.isoformat(),
                "set_meals": " からあげ定食 \n\n親子丼定食",
                "donburi": "",
                "menu_text": "",
            }
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.set_meal_names(), ["からあげ定食", "親子丼定食"])
        self.assertEqual(form.donburi_names(), [])
        menu, created = canteen_service.save_menu(form, self.user)
        self.assertTrue(created)
        self.assertEqual(self._names(menu), ["からあげ定食", "親子丼定食"])
