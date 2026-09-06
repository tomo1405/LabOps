"""学食メニューの保存をまとめて行うサービス。

メニュー本体の作成・更新、置換先の削除、品目の置き換えを1つのトランザクションで行い、
対象日付の既存メニューをロックして同じ日への登録・編集を直列化する。

「登録・編集のたびに、その日の品目を入力内容で置き換える」という仕様を、
保存に失敗した場合や同時に登録された場合でも保つための入口。
"""

from datetime import date as date_type

from django.db import IntegrityError, transaction

from .models import CanteenMenu, CanteenMenuItem, MenuCategory, MenuSource


def _lock_menu(day: date_type, exclude_pk: int | None = None) -> CanteenMenu | None:
    """その日付の既存メニューを行ロック付きで取得する。"""
    menus = CanteenMenu.objects.select_for_update().filter(date=day)
    if exclude_pk is not None:
        menus = menus.exclude(pk=exclude_pk)
    return menus.first()


def _get_or_create_locked(day: date_type) -> tuple[CanteenMenu, bool]:
    """その日付のメニューをロック付きで取得する。無ければ作成する。

    未登録日への同時作成は一意制約違反になるため、
    その場合は先に作られたメニューを読み直して上書き処理へ合流させる。
    """
    existing = _lock_menu(day)
    if existing is not None:
        return existing, False
    try:
        # 失敗しても外側のトランザクションを壊さないよう savepoint で包む
        with transaction.atomic():
            return CanteenMenu.objects.create(date=day), True
    except IntegrityError:
        return CanteenMenu.objects.select_for_update().get(date=day), False


def _replace_items(menu: CanteenMenu, set_meal_names: list[str], donburi_names: list[str]) -> None:
    """入力された品目で登録済みの内容を置き換える。"""
    menu.items.all().delete()
    CanteenMenuItem.objects.bulk_create(
        [
            CanteenMenuItem(menu=menu, category=category, name=name, position=position)
            for category, names in (
                (MenuCategory.SET_MEAL, set_meal_names),
                (MenuCategory.DONBURI, donburi_names),
            )
            for position, name in enumerate(names)
        ]
    )


@transaction.atomic
def save_menu(form, user, menu: CanteenMenu | None = None) -> tuple[CanteenMenu, bool]:
    """フォームの内容でその日のメニューを保存する。

    日付ごとに1件のため、同じ日付に既存の登録があれば上書きする
    （編集で日付を別の日へ移した場合も同じ）。
    戻り値は (保存したメニュー, 新規作成したか)。
    """
    day = form.cleaned_data["date"]

    if menu is None:
        target, created = _get_or_create_locked(day)
    else:
        # 別の日付へ移す場合、その日の既存登録は上書きして重複を作らない
        conflicting = _lock_menu(day, exclude_pk=menu.pk)
        if conflicting is not None:
            conflicting.delete()
        target, created = menu, False

    target.date = day
    target.menu_text = form.cleaned_data["menu_text"]
    target.source = MenuSource.MANUAL
    # 直したのが誰かが分かるよう、最後に編集した人を登録者にする
    target.registered_by = user
    target.save()
    _replace_items(target, form.set_meal_names(), form.donburi_names())
    return target, created
