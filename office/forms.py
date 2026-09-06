"""優先度4: 事務系のフォーム。"""

from django import forms

from .models import TravelExpenseRequest


class TravelExpenseRequestForm(forms.ModelForm):
    """出張費申請フォーム（詳細設計書 4章 GET/POST /travel-expenses/）。"""

    class Meta:
        model = TravelExpenseRequest
        fields = ["destination", "purpose", "amount", "travel_start", "travel_end"]
        widgets = {
            "destination": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "例: 京都大学（言語処理学会 年次大会）"}
            ),
            "purpose": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "例: 言語処理学会 年次大会での口頭発表",
                }
            ),
            "amount": forms.NumberInput(attrs={"class": "form-control", "min": 1, "step": 1}),
            "travel_start": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "travel_end": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }
        labels = {"amount": "金額（円）"}
        help_texts = {"amount": "交通費・宿泊費・参加費の合計（概算で可）"}

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("金額は1円以上で入力してください。")
        return amount

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("travel_start"), cleaned.get("travel_end")
        if start and end and end < start:
            self.add_error("travel_end", "出張終了日は開始日以降にしてください。")
        return cleaned
