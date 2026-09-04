#!/usr/bin/env python
"""Django のコマンドラインユーティリティ。"""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Django をインポートできません。仮想環境を有効化しているか確認してください。"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
