"""優先度1: 研究支援系のフォーム。"""

from django import forms
from django.utils import timezone

from .models import ConferenceChecklistItem, ConferencePrep, DiaryEntry, ScheduleEvent


class DiaryEntryForm(forms.ModelForm):
    class Meta:
        model = DiaryEntry
        fields = ["date", "content", "tags", "visibility"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "content": forms.Textarea(attrs={"class": "form-control", "rows": 12}),
            "tags": forms.TextInput(attrs={"class": "form-control", "placeholder": "実験, 論文読み"}),
            "visibility": forms.RadioSelect(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields["date"].initial = timezone.localdate()
        self.fields[
            "content"
        ].help_text = "Markdownで書けます（## 見出し / - 箇条書き / **強調** / `コード` / 表）"


class ScheduleEventForm(forms.ModelForm):
    class Meta:
        model = ScheduleEvent
        fields = ["title", "start_at", "end_at", "event_type", "conference", "user"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "start_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "end_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "event_type": forms.Select(attrs={"class": "form-select"}),
            "conference": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        """user を渡すと、その人の学会準備のみ紐付け候補にする。"""
        super().__init__(*args, **kwargs)
        # 予定の所有者はビュー側で決めるため、フォームには出さない
        self.fields["user"].required = False
        self.fields["user"].widget = forms.HiddenInput()
        self.fields["conference"].required = False
        self.fields["conference"].empty_label = "（紐付けなし）"
        if user is not None:
            self.fields["conference"].queryset = ConferencePrep.objects.filter(user=user)

    def clean(self):
        cleaned = super().clean()
        start_at, end_at = cleaned.get("start_at"), cleaned.get("end_at")
        if start_at and end_at and end_at < start_at:
            self.add_error("end_at", "終了日時は開始日時以降にしてください。")
        return cleaned


class ConferencePrepForm(forms.ModelForm):
    checklist_items = forms.CharField(
        label="チェックリスト項目",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5, "placeholder": "1行に1項目"}),
        help_text="1行に1項目を入力してください（後から追加もできます）",
    )

    class Meta:
        model = ConferencePrep
        fields = ["conference_name", "deadline"]
        widgets = {
            "conference_name": forms.TextInput(attrs={"class": "form-control"}),
            "deadline": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }

    def initial_checklist_items(self) -> list[str]:
        """入力されたチェックリスト項目を1行1項目として取り出す。"""
        raw = self.cleaned_data.get("checklist_items", "")
        return [line.strip() for line in raw.splitlines() if line.strip()]


class ConferenceChecklistItemForm(forms.ModelForm):
    class Meta:
        model = ConferenceChecklistItem
        fields = ["item"]
        widgets = {
            "item": forms.TextInput(
                attrs={"class": "form-control form-control-sm", "placeholder": "追加する項目"}
            ),
        }
