"""優先度2: 情報共有・コミュニケーション系のフォーム。"""

from django import forms
from django.utils import timezone

from .models import (
    CanteenMenu,
    CanteenMenuItem,
    MeetingRoom,
    NewsPost,
    RoomReservation,
)


class CanteenMenuForm(forms.ModelForm):
    """学食メニューの登録フォーム（詳細設計書 4章 POST /canteen/）。

    献立は「定食」「アラカルト丼」の区分ごとに、1行1品で入力する。
    品名の制約はモデル側（CanteenMenuItem.name）と揃え、DB保存時ではなく
    フォーム段階で弾く。SQLiteとPostgreSQLで結果が変わらないようにするため。
    """

    # 制約値を二重に持たないよう、モデルの定義をそのまま参照する
    ITEM_MAX_LENGTH = CanteenMenuItem._meta.get_field("name").max_length
    # 1区分あたりの品目数の上限。過大な入力をフォーム段階で拒否する
    MAX_ITEMS = 50

    set_meals = forms.CharField(
        label="定食",
        required=False,
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 4, "placeholder": "からあげ定食\n鯖の味噌煮定食"}
        ),
        help_text=f"1行に1品（1品{ITEM_MAX_LENGTH}文字以内、{MAX_ITEMS}品まで）",
    )
    donburi = forms.CharField(
        label="アラカルト丼",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "親子丼\n海鮮丼"}),
        help_text=f"1行に1品（1品{ITEM_MAX_LENGTH}文字以内、{MAX_ITEMS}品まで）",
    )

    # 入力欄の並び（日付 → 定食 → 丼 → 補足）
    field_order = ["date", "set_meals", "donburi", "menu_text"]

    class Meta:
        model = CanteenMenu
        fields = ["date", "menu_text"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "menu_text": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": "麺コーナー: 天ぷらうどん"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["date"].initial = timezone.localdate()
        else:
            # 編集時は登録済みの品目を1行1品で流し込む
            self.fields["set_meals"].initial = "\n".join(item.name for item in self.instance.set_meals)
            self.fields["donburi"].initial = "\n".join(item.name for item in self.instance.donburi)
        # 同じ日付の再登録は上書き扱いにするため、モデル側の unique 検証は行わない
        self.fields["date"].validators = []

    def validate_unique(self) -> None:
        """日付の重複はビュー側で上書きとして扱うため、検証しない。"""
        return

    def _clean_names(self, raw: str) -> list[str]:
        """1行1品として取り出し、空行を除いたうえで品名を検証する。

        モデルの max_length はDBによっては強制されないため、ここで必ず検証して
        開発（SQLite）と本番（PostgreSQL）で結果が変わらないようにする。
        """
        names: list[str] = []
        too_long: list[int] = []
        for lineno, line in enumerate((raw or "").splitlines(), start=1):
            name = line.strip()
            if not name:
                continue
            if len(name) > self.ITEM_MAX_LENGTH:
                too_long.append(lineno)
            names.append(name)
        if too_long:
            lines = "、".join(f"{n}行目" for n in too_long)
            raise forms.ValidationError(
                f"{lines}が長すぎます。1品は{self.ITEM_MAX_LENGTH}文字以内にしてください。"
            )
        if len(names) > self.MAX_ITEMS:
            raise forms.ValidationError(f"品目が多すぎます。1区分{self.MAX_ITEMS}品までにしてください。")
        return names

    def clean_set_meals(self) -> list[str]:
        return self._clean_names(self.cleaned_data.get("set_meals", ""))

    def clean_donburi(self) -> list[str]:
        return self._clean_names(self.cleaned_data.get("donburi", ""))

    def set_meal_names(self) -> list[str]:
        """検証済みの定食の品名（空行は除去済み）。"""
        return self.cleaned_data.get("set_meals") or []

    def donburi_names(self) -> list[str]:
        """検証済みのアラカルト丼の品名（空行は除去済み）。"""
        return self.cleaned_data.get("donburi") or []

    def clean(self):
        cleaned = super().clean()
        if self.has_error("set_meals") or self.has_error("donburi"):
            # 品名のエラーが出ているときは、未入力扱いの追加エラーを重ねない
            return cleaned
        if not (self.set_meal_names() or self.donburi_names() or cleaned.get("menu_text")):
            raise forms.ValidationError("定食・アラカルト丼・補足のいずれかを入力してください。")
        return cleaned


class NewsPostForm(forms.ModelForm):
    """News記事の投稿フォーム（詳細設計書 4章 GET/POST /news/new）。"""

    class Meta:
        model = NewsPost
        fields = ["title", "body"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "body": forms.Textarea(attrs={"class": "form-control", "rows": 10}),
        }


class RoomReservationForm(forms.ModelForm):
    """会議室の予約フォーム。重なりの判定はモデルの clean() で行う。"""

    class Meta:
        model = RoomReservation
        fields = ["room", "purpose", "start_at", "end_at"]
        widgets = {
            "room": forms.Select(attrs={"class": "form-select"}),
            "purpose": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "例: 研究ミーティング"}
            ),
            "start_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "end_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["room"].queryset = MeetingRoom.objects.filter(is_active=True)
        self.fields["room"].empty_label = None
