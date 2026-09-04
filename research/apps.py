from django.apps import AppConfig


class ResearchConfig(AppConfig):
    name = "research"
    verbose_name = "研究支援（優先度1）"

    def ready(self) -> None:
        # 添付ファイルの実体削除シグナルを登録する
        from . import signals  # noqa: F401
