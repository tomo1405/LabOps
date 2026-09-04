"""研究日記の添付ファイルの形式判定（REV-002 の入力検証とREV-001の配信で共用）。

方針:
- 研究室内で実際に使う形式だけを許可する（拡張子のホワイトリスト）。
- 拡張子とファイルの中身（シグネチャ）が一致することを確認する。
- クライアントが申告した Content-Type は信用せず、拡張子から一意に決める。
- HTML・SVG・JavaScript などの能動的コンテンツは許可しない。
"""

from pathlib import Path

# 画面に埋め込んで表示する画像形式
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp")

# 拡張子 -> サーバー側で決める Content-Type
CONTENT_TYPES: dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".json": "application/json",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".zip": "application/zip",
}

ALLOWED_SUFFIXES = tuple(CONTENT_TYPES)

# 拡張子 -> 先頭に現れるべきバイト列（いずれか1つに一致すればよい）
_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".pdf": (b"%PDF-",),
    # OOXML（xlsx/docx/pptx）とzipはいずれもZIPコンテナ
    ".xlsx": (b"PK\x03\x04",),
    ".docx": (b"PK\x03\x04",),
    ".pptx": (b"PK\x03\x04",),
    ".zip": (b"PK\x03\x04", b"PK\x05\x06"),
}

# シグネチャを持たないテキスト系。中身がテキストであることだけを確認する
_TEXT_SUFFIXES = (".csv", ".tsv", ".txt", ".md", ".json")

# 先頭バイトを読む長さ。WebP の判定に必要な12バイトを超えるよう余裕を持たせる
_HEAD_SIZE = 512


def suffix_of(filename: str) -> str:
    """ファイル名から小文字の拡張子を取り出す。"""
    return Path(filename).suffix.lower()


def safe_original_name(filename: str) -> str:
    """表示・ヘッダー用に安全化した元のファイル名。

    ディレクトリ成分と制御文字を除去する。制御文字を残すと
    Content-Disposition ヘッダーの生成時に不正なレスポンスになる。
    """
    name = Path(filename.replace("\\", "/")).name
    cleaned = "".join(c for c in name if c.isprintable())
    return cleaned[:255] or "attachment"


def is_image_name(filename: str) -> bool:
    """画面に埋め込んで表示できる画像か。"""
    return suffix_of(filename) in IMAGE_SUFFIXES


def content_type_for(filename: str) -> str:
    """拡張子から決めた Content-Type。未知の形式は汎用のバイナリ扱い。"""
    return CONTENT_TYPES.get(suffix_of(filename), "application/octet-stream")


def is_allowed_suffix(filename: str) -> bool:
    """許可された拡張子か。"""
    return suffix_of(filename) in CONTENT_TYPES


def matches_signature(head: bytes, filename: str) -> bool:
    """先頭バイト列が拡張子と整合するか。

    head には少なくとも先頭 _HEAD_SIZE バイトを渡す。
    """
    suffix = suffix_of(filename)
    if suffix == ".webp":
        # RIFF????WEBP（4バイトのサイズを挟む）
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if suffix in _SIGNATURES:
        return head.startswith(_SIGNATURES[suffix])
    if suffix in _TEXT_SUFFIXES:
        # NULバイトを含むものはテキストではないと判断する
        return b"\x00" not in head
    return False


def read_head(uploaded) -> bytes:
    """アップロードファイルの先頭バイトを読み、位置を戻す。"""
    uploaded.seek(0)
    head = uploaded.read(_HEAD_SIZE)
    uploaded.seek(0)
    return head
