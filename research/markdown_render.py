"""ユーザー入力のMarkdownを安全にHTMLへ変換する。

Markdown中にHTMLを直接書けるため、変換後は必ずサニタイズしてから表示する。
"""

import markdown as markdown_lib
import nh3

# 研究記録で使う範囲に絞る。script/style/iframe などは許可しない
ALLOWED_TAGS = {
    "p",
    "br",
    "hr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "strong",
    "em",
    "del",
    "blockquote",
    "ul",
    "ol",
    "li",
    "code",
    "pre",
    "a",
    "img",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title"},
    "td": {"align"},
    "th": {"align"},
}
ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


def render_markdown(text: str) -> str:
    """MarkdownをHTMLへ変換し、許可したタグ・属性だけを残して返す。"""
    html = markdown_lib.markdown(
        text or "",
        extensions=["extra", "sane_lists", "nl2br"],
        output_format="html",
    )
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer",
    )
