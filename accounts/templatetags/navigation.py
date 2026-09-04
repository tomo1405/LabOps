"""ナビゲーションの現在地表示に使うテンプレートタグ。

画面をまたいで使うため、認証まわりを持つ accounts に置いている。
"""

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def nav_active(context, *prefixes: str) -> str:
    """現在の画面が指定したURL名で始まるとき "active" を返す。

    詳細・編集・削除など下位の画面でも、親のメニューが選択状態になるように
    URL名の前方一致で判定する（例: "research:diary" は diary_detail にも一致）。
    """
    request = context.get("request")
    match = getattr(request, "resolver_match", None)
    if match is None:
        return ""
    current = f"{match.namespace}:{match.url_name}" if match.namespace else (match.url_name or "")
    return "active" if any(current.startswith(prefix) for prefix in prefixes) else ""
