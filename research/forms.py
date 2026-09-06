"""優先度1: 研究支援系のフォーム。"""

from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone

from . import attachments
from .models import (
    ConferenceChecklistItem,
    ConferencePrep,
    DiaryAttachment,
    DiaryComment,
    DiaryEntry,
    ScheduleEvent,
)


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


class DiaryAttachmentForm(forms.ModelForm):
    """研究日記への添付フォーム。

    サイズ上限に加えて、研究室内で使う形式だけを許可する。
    HTMLやSVGなどの能動的コンテンツを同一オリジンから配信させないため、
    拡張子のホワイトリストと中身のシグネチャの両方を検証する。
    """

    MAX_SIZE_MB = 10

    class Meta:
        model = DiaryAttachment
        fields = ["file"]
        widgets = {
            "file": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                    "accept": ",".join(attachments.ALLOWED_SUFFIXES),
                }
            )
        }

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        limit = self.MAX_SIZE_MB * 1024 * 1024
        if uploaded.size > limit:
            raise forms.ValidationError(f"ファイルサイズが上限（{self.MAX_SIZE_MB}MB）を超えています。")

        # クライアントが申告する Content-Type は信用せず、拡張子で判定する
        if not attachments.is_allowed_suffix(uploaded.name):
            allowed = " / ".join(s.lstrip(".").upper() for s in attachments.ALLOWED_SUFFIXES)
            raise forms.ValidationError(
                f"この形式のファイルは添付できません。添付できるのは {allowed} です。"
            )
        if not attachments.matches_signature(attachments.read_head(uploaded), uploaded.name):
            raise forms.ValidationError("ファイルの中身が拡張子と一致しません。")

        # ディレクトリ成分や制御文字を落としてから保存名に使う
        uploaded.name = attachments.safe_original_name(uploaded.name)
        return uploaded


class DiaryCommentForm(forms.ModelForm):
    """研究日記へのコメントフォーム。"""

    class Meta:
        model = DiaryComment
        fields = ["body"]
        widgets = {
            "body": forms.Textarea(
                attrs={"class": "form-control", "rows": 3, "placeholder": "コメントを書く"}
            ),
        }
        labels = {"body": "コメント"}


class ScheduleEventForm(forms.ModelForm):
    class Meta:
        model = ScheduleEvent
        fields = ["title", "start_at", "end_at", "event_type", "conference", "participants", "user"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "start_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "end_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "event_type": forms.Select(attrs={"class": "form-select"}),
            "conference": forms.Select(attrs={"class": "form-select"}),
            "participants": forms.CheckboxSelectMultiple(),
        }

    def __init__(self, *args, user=None, **kwargs):
        """user を渡すと、その人の学会準備のみ紐付け候補にする。"""
        super().__init__(*args, **kwargs)
        # 予定の所有者はビュー側で決めるため、フォームには出さない
        self.fields["user"].required = False
        self.fields["user"].widget = forms.HiddenInput()
        self.fields["conference"].required = False
        self.fields["conference"].empty_label = "（紐付けなし）"
        self.fields["participants"].required = False
        if user is not None:
            self.fields["conference"].queryset = ConferencePrep.objects.filter(user=user)
            # 作成者自身は常に予定に含まれるため、参加者の候補から外す
            self.fields["participants"].queryset = (
                get_user_model().objects.filter(is_active=True).exclude(pk=user.pk)
            )

    def clean(self):
        cleaned = super().clean()
        start_at, end_at = cleaned.get("start_at"), cleaned.get("end_at")
        if start_at and end_at and end_at < start_at:
            self.add_error("end_at", "終了日時は開始日時以降にしてください。")
        return cleaned


class ConferencePrepForm(forms.ModelForm):
    """学会準備の登録・編集フォーム。

    チェックリスト項目は改行区切りでまとめて受け取るが、
    個別追加（ConferenceChecklistItemForm）と同じ長さ制約を適用する。
    """

    # 制約値を二重に持たないよう、モデルの定義をそのまま参照する
    ITEM_MAX_LENGTH = ConferenceChecklistItem._meta.get_field("item").max_length

    checklist_items = forms.CharField(
        label="チェックリスト項目",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 5, "placeholder": "1行に1項目"}),
        help_text=f"1行に1項目を入力してください（1項目{ITEM_MAX_LENGTH}文字以内。後から追加もできます）",
    )

    class Meta:
        model = ConferencePrep
        fields = ["conference_name", "deadline"]
        widgets = {
            "conference_name": forms.TextInput(attrs={"class": "form-control"}),
            "deadline": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        }

    def clean_checklist_items(self) -> list[str]:
        """1行1項目として取り出し、空行を除いたうえで長さを検証する。

        モデルの max_length はDBによっては強制されないため、
        ここで必ず検証して環境差が出ないようにする。
        """
        raw = self.cleaned_data.get("checklist_items", "")
        items: list[str] = []
        too_long: list[int] = []
        for lineno, line in enumerate(raw.splitlines(), start=1):
            item = line.strip()
            if not item:
                continue
            if len(item) > self.ITEM_MAX_LENGTH:
                too_long.append(lineno)
            items.append(item)
        if too_long:
            lines = "、".join(f"{n}行目" for n in too_long)
            raise forms.ValidationError(
                f"{lines}が長すぎます。1項目は{self.ITEM_MAX_LENGTH}文字以内にしてください。"
            )
        return items

    def initial_checklist_items(self) -> list[str]:
        """検証済みのチェックリスト項目（空行は除去済み）。"""
        return self.cleaned_data.get("checklist_items", [])


class ConferenceChecklistItemForm(forms.ModelForm):
    class Meta:
        model = ConferenceChecklistItem
        fields = ["item"]
        widgets = {
            "item": forms.TextInput(
                attrs={"class": "form-control form-control-sm", "placeholder": "追加する項目"}
            ),
        }
