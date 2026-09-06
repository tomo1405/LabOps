"""会議室の並び順を、研究室で使う順に設定する。"""

from django.db import migrations

# 表示したい順。名称が一致する部屋にだけ設定する
ROOM_ORDER = [
    "全体ミーティングルーム",
    "ミーティングルーム",
    "サーバルーム",
    "ゲームルーム",
]


def set_order(apps, schema_editor):
    MeetingRoom = apps.get_model("community", "MeetingRoom")
    for position, name in enumerate(ROOM_ORDER):
        MeetingRoom.objects.filter(name=name).update(position=position)


class Migration(migrations.Migration):
    dependencies = [("community", "0009_alter_meetingroom_options_meetingroom_position_and_more")]

    operations = [migrations.RunPython(set_order, migrations.RunPython.noop)]
