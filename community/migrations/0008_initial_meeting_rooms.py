"""研究室の会議室を初期データとして登録する。

部屋は運用で決まっているため、環境ごとに手作業で登録しなくて済むよう
マイグレーションで投入する。名称が一致するものがあれば作らない。
"""

from django.db import migrations

INITIAL_ROOMS = [
    ("全体ミーティングルーム", "B307"),
    ("ミーティングルーム", "B303"),
    ("サーバルーム", "B304"),
    ("ゲームルーム", "B305"),
]


def create_rooms(apps, schema_editor):
    MeetingRoom = apps.get_model("community", "MeetingRoom")
    for name, location in INITIAL_ROOMS:
        MeetingRoom.objects.get_or_create(name=name, defaults={"location": location})


def remove_rooms(apps, schema_editor):
    """巻き戻し時は、予約が入っていない部屋だけ削除する（予約を巻き込まないため）。"""
    MeetingRoom = apps.get_model("community", "MeetingRoom")
    for name, _ in INITIAL_ROOMS:
        MeetingRoom.objects.filter(name=name, reservations__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [("community", "0007_meetingroom_roomreservation")]

    operations = [migrations.RunPython(create_rooms, remove_rooms)]
