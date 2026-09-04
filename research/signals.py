"""研究支援系のシグナル。

添付ファイルのライフサイクル管理に使う。Django の FileField は行を削除しても
ストレージ上の実体を消さないため、post_delete で明示的に削除する。
ビュー・日記のCASCADE削除・ユーザー削除・管理画面・QuerySetの一括削除の
すべてでこのシグナルが発火するので、経路ごとの実装が不要になる。
"""

import logging

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import DiaryAttachment

logger = logging.getLogger(__name__)


@receiver(post_delete, sender=DiaryAttachment)
def delete_attachment_file(sender, instance: DiaryAttachment, **kwargs) -> None:
    """添付レコードの削除に合わせてストレージ上の実体も削除する。

    削除がロールバックされた場合にファイルだけ失われるのを避けるため、
    実際の削除はトランザクションのコミット後に行う。
    """
    if not instance.file:
        return

    file_field = instance.file
    name = file_field.name

    def _delete_from_storage() -> None:
        try:
            # save=False: 行はすでに削除済みなのでDB更新はしない
            file_field.delete(save=False)
        except OSError:
            # 実体の削除に失敗してもDB側の削除は取り消せない。
            # 残留ファイルは記録を頼りに後から手動で回収する。
            logger.exception("添付ファイルの実体を削除できませんでした: %s", name)

    transaction.on_commit(_delete_from_storage)
