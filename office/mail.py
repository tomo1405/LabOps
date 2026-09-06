"""出張費申請の通知メール。"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMessage
from django.urls import reverse

from accounts.models import Role


def resolve_recipients() -> list[str]:
    """送信先。設定がなければ教員ロールのメールアドレスを使う。

    設定と教員の両方が空の場合は空リストを返し、呼び出し側で送信を諦める。
    """
    if settings.TRAVEL_EXPENSE_RECIPIENTS:
        return list(settings.TRAVEL_EXPENSE_RECIPIENTS)
    return list(
        get_user_model()
        .objects.filter(role=Role.FACULTY, is_active=True)
        .exclude(email="")
        .values_list("email", flat=True)
    )


def build_message(request_obj) -> EmailMessage:
    """申請内容のメールを組み立てる。返信すると申請者に届くようにする。"""
    applicant = request_obj.user
    body = "\n".join(
        [
            "出張費の申請がありました。",
            "",
            f"申請者　: {applicant.name}（{applicant.email}）",
            f"出張先　: {request_obj.destination}",
            f"期間　　: {request_obj.travel_start} 〜 {request_obj.travel_end}",
            f"金額　　: {int(request_obj.amount):,} 円",
            "目的　　:",
            request_obj.purpose,
            "",
            f"申請一覧: {reverse('office:travel_expense_list')}",
            "（LabOps から自動送信）",
        ]
    )
    message = EmailMessage(
        subject=f"[LabOps] 出張費申請: {applicant.name} / {request_obj.destination}",
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=resolve_recipients(),
        reply_to=[applicant.email] if applicant.email else None,
    )
    return message


def send_travel_expense_mail(request_obj) -> tuple[bool, str]:
    """申請内容をメールで送る。

    送信できたかと、できなかった理由を返す。申請そのものは保存済みなので、
    送信に失敗しても処理は止めず、画面で知らせる。
    """
    message = build_message(request_obj)
    if not message.to:
        return False, "送信先が設定されていません（教員のメールアドレスも未登録です）。"
    try:
        message.send(fail_silently=False)
    except Exception as exc:  # noqa: BLE001 - 送信失敗の理由をそのまま画面に出す
        return False, str(exc)
    return True, ""
