"""NFCタグをユーザーごとの個人タグに変更する。

旧方式（設置場所を表すタグ＋ログインで本人を判定）のタグは、
URLの意味が変わって使えなくなるため削除する。
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def delete_location_tags(apps, schema_editor):
    apps.get_model("community", "NfcTag").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("community", "0003_nfctag_attendancelog"),
    ]

    operations = [
        migrations.RunPython(delete_location_tags, migrations.RunPython.noop),
        migrations.AddField(
            model_name="nfctag",
            name="user",
            field=models.ForeignKey(
                default=None,
                help_text="このタグを読んだときに入退室が切り替わるメンバー",
                on_delete=django.db.models.deletion.CASCADE,
                related_name="nfc_tags",
                to=settings.AUTH_USER_MODEL,
                verbose_name="対象メンバー",
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="nfctag",
            name="label",
            field=models.CharField(
                blank=True, help_text="例: 入り口に貼るタグ（予備）", max_length=50, verbose_name="名称"
            ),
        ),
        migrations.AlterModelOptions(
            name="nfctag",
            options={
                "ordering": ["user__name", "label"],
                "verbose_name": "NFCタグ",
                "verbose_name_plural": "NFCタグ",
            },
        ),
    ]
