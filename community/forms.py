"""優先度2: 情報共有・コミュニケーション系のフォーム。"""

from django import forms
from django.utils import timezone

from .models import CanteenMenu, NewsPost


class CanteenMenuForm(forms.ModelForm):
    """学食メニューの登録フォーム（詳細設計書 4章 POST /canteen/）。"""

    class Meta:
        model = CanteenMenu
        fields = ["date", "menu_text"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "menu_text": forms.Textarea(
                attrs={"class": "form-control", "rows": 4, "placeholder": "A定食: ...\nB定食: ..."}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["date"].initial = timezone.localdate()
        # 同じ日付の再登録は上書き扱いにするため、モデル側の unique 検証は行わない
        self.fields["date"].validators = []

    def validate_unique(self) -> None:
        """日付の重複はビュー側で上書きとして扱うため、検証しない。"""
        return


class NewsPostForm(forms.ModelForm):
    """News記事の投稿フォーム（詳細設計書 4章 GET/POST /news/new）。"""

    class Meta:
        model = NewsPost
        fields = ["title", "body"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "body": forms.Textarea(attrs={"class": "form-control", "rows": 10}),
        }
