"""学食メニューの品目（定食・アラカルト丼）のテスト。"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from community.models import CanteenMenu, CanteenMenuItem, MenuCategory

User = get_user_model()


class CanteenMenuItemTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="me@example.com", password="pw12345!", name="本人")

    def setUp(self):
        self.client.force_login(self.user)
        self.today = timezone.localdate()

    def _post(self, url, **overrides):
        data = {
            "date": self.today.isoformat(),
            "set_meals": "からあげ定食\n鯖の味噌煮定食",
            "donburi": "親子丼",
            "menu_text": "",
        }
        data.update(overrides)
        return self.client.post(url, data)

    def test_register_items_by_category(self):
        response = self._post(reverse("community:canteen_create"))
        self.assertRedirects(response, reverse("community:canteen_today"))

        menu = CanteenMenu.objects.get()
        self.assertEqual([i.name for i in menu.set_meals], ["からあげ定食", "鯖の味噌煮定食"])
        self.assertEqual([i.name for i in menu.donburi], ["親子丼"])

    def test_items_keep_input_order(self):
        self._post(reverse("community:canteen_create"))
        positions = list(
            CanteenMenuItem.objects.filter(category=MenuCategory.SET_MEAL)
            .order_by("position")
            .values_list("name", "position")
        )
        self.assertEqual(positions, [("からあげ定食", 0), ("鯖の味噌煮定食", 1)])

    def test_blank_lines_are_ignored(self):
        self._post(reverse("community:canteen_create"), set_meals="からあげ定食\n\n  \n日替わり定食")
        menu = CanteenMenu.objects.get()
        self.assertEqual([i.name for i in menu.set_meals], ["からあげ定食", "日替わり定食"])

    def test_only_donburi_is_allowed(self):
        self._post(reverse("community:canteen_create"), set_meals="", donburi="海鮮丼")
        menu = CanteenMenu.objects.get()
        self.assertEqual([i.name for i in menu.set_meals], [])
        self.assertEqual([i.name for i in menu.donburi], ["海鮮丼"])

    def test_note_only_is_allowed(self):
        """定食・丼がなくても、補足だけで登録できる（臨時休業など）。"""
        self._post(reverse("community:canteen_create"), set_meals="", donburi="", menu_text="本日休業")
        menu = CanteenMenu.objects.get()
        self.assertEqual(menu.menu_text, "本日休業")
        self.assertFalse(menu.items.exists())

    def test_all_blank_is_rejected(self):
        response = self._post(reverse("community:canteen_create"), set_meals="", donburi="", menu_text="")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CanteenMenu.objects.exists())

    def test_re_registering_replaces_items(self):
        """同じ日付で登録し直すと、品目は置き換わる（重複しない）。"""
        self._post(reverse("community:canteen_create"))
        self._post(reverse("community:canteen_create"), set_meals="日替わり定食", donburi="")

        menu = CanteenMenu.objects.get()
        self.assertEqual([i.name for i in menu.set_meals], ["日替わり定食"])
        self.assertEqual([i.name for i in menu.donburi], [])
        self.assertEqual(CanteenMenuItem.objects.count(), 1)

    def test_edit_form_prefills_registered_items(self):
        self._post(reverse("community:canteen_create"))
        menu = CanteenMenu.objects.get()

        response = self.client.get(reverse("community:canteen_update", args=[menu.pk]))
        form = response.context["form"]
        self.assertEqual(form["set_meals"].value(), "からあげ定食\n鯖の味噌煮定食")
        self.assertEqual(form["donburi"].value(), "親子丼")

    def test_edit_replaces_items(self):
        self._post(reverse("community:canteen_create"))
        menu = CanteenMenu.objects.get()

        self._post(
            reverse("community:canteen_update", args=[menu.pk]),
            set_meals="日替わり定食",
            donburi="カツ丼\n天丼",
        )
        menu.refresh_from_db()
        self.assertEqual([i.name for i in menu.set_meals], ["日替わり定食"])
        self.assertEqual([i.name for i in menu.donburi], ["カツ丼", "天丼"])

    def test_deleting_menu_removes_items(self):
        self._post(reverse("community:canteen_create"))
        menu = CanteenMenu.objects.get()
        self.client.post(reverse("community:canteen_delete", args=[menu.pk]))
        self.assertFalse(CanteenMenuItem.objects.exists())

    def test_today_page_shows_categories(self):
        self._post(reverse("community:canteen_create"))
        response = self.client.get(reverse("community:canteen_today"))
        self.assertContains(response, "定食")
        self.assertContains(response, "アラカルト丼")
        self.assertContains(response, "からあげ定食")
        self.assertContains(response, "親子丼")

    def test_history_shows_items_of_past_days(self):
        yesterday = self.today - timedelta(days=1)
        self._post(reverse("community:canteen_create"), date=yesterday.isoformat())
        response = self.client.get(reverse("community:canteen_today"))
        self.assertContains(response, "からあげ定食")

    def test_dashboard_shows_today_items(self):
        self._post(reverse("community:canteen_create"))
        response = self.client.get(reverse("research:dashboard"))
        self.assertContains(response, "からあげ定食")
        self.assertContains(response, "親子丼")

    def test_is_empty_detects_menu_without_content(self):
        menu = CanteenMenu.objects.create(date=self.today)
        self.assertTrue(menu.is_empty)
        CanteenMenuItem.objects.create(menu=menu, category=MenuCategory.DONBURI, name="親子丼")
        self.assertFalse(menu.is_empty)
