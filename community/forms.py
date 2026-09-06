"""優先度2: 情報共有・コミュニケーション系のフォーム。"""

from django import forms
from django.utils import timezone

from .models import CanteenMenu, NewsPost


class CanteenMenuForm(forms.ModelForm):
    """学食メニューの登録フォーム（詳細設計書 4章 POST /canteen/）。

    献立は「定食」「アラカルト丼」の区分ごとに、1行1品で入力する。
    """

    set_meals = forms.CharField(
        label="定食",
        required=False,
        widget=forms.Textarea(
            attrs={"class": "form-control", "rows": 4, "placeholder": "からあげ定食\n鯖の味噌煮定食"}
        ),
        help_text="1行に1品",
    )
    donburi = forms.CharField(
        label="アラカルト丼",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "親子丼\n海鮮丼"}),
        help_text="1行に1品",
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

    @staticmethod
    def _lines(raw: str) -> list[str]:
        return [line.strip() for line in (raw or "").splitlines() if line.strip()]

    def set_meal_names(self) -> list[str]:
        return self._lines(self.cleaned_data.get("set_meals", ""))

    def donburi_names(self) -> list[str]:
        return self._lines(self.cleaned_data.get("donburi", ""))

    def clean(self):
        cleaned = super().clean()
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
