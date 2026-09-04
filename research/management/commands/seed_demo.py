"""ローカル動作確認用のデモデータを投入する開発専用コマンド。

本番環境で実行されないよう、DEBUG=True のときだけ動作する。
"""

from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Role
from research.models import (
    ConferenceChecklistItem,
    ConferencePrep,
    DiaryEntry,
    EventType,
    ScheduleEvent,
)

User = get_user_model()

# ローカル確認用の固定パスワード（開発専用。本番では createsuperuser を使う）
DEMO_PASSWORD = "demo-pass-12345"

DEMO_USERS = [
    ("teacher@example.local", "指導教員", Role.FACULTY, True),
    ("student@example.local", "学生ユーザー", Role.STUDENT, False),
]

DEMO_DIARIES = [
    (0, "提案手法の学習を回した。学習率 1e-4 が安定していそう。", "実験, 学習"),
    (1, "関連研究を3本読んだ。評価指標の扱いが論文ごとに違う点を整理。", "論文読み"),
    (3, "前処理のバグを修正。データ件数が想定より少なかった原因が判明した。", "実装, デバッグ"),
]

DEMO_CHECKLIST = [
    ("要旨の執筆", True),
    ("実験結果の図表作成", True),
    ("原稿の初稿", False),
    ("指導教員のレビュー反映", False),
    ("発表スライド作成", False),
]


class Command(BaseCommand):
    help = "ローカル動作確認用のデモユーザーと優先度①のデモデータを投入する（DEBUG時のみ）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="デモユーザーに紐づく既存のデモデータを削除してから投入する",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo は開発用コマンドです。DJANGO_DEBUG=1 の環境で実行してください。")

        users = {}
        for email, name, role, is_staff in DEMO_USERS:
            user, created = User.objects.get_or_create(
                email=email,
                defaults={"name": name, "role": role, "is_staff": is_staff, "is_superuser": is_staff},
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save(update_fields=["password"])
            users[email] = user
            self.stdout.write(f"{'作成' if created else '既存'}: {email}（{name}）")

        student = users["student@example.local"]

        if options["reset"]:
            DiaryEntry.objects.filter(user=student).delete()
            ScheduleEvent.objects.filter(user=student).delete()
            ConferencePrep.objects.filter(user=student).delete()
            self.stdout.write("既存のデモデータを削除しました。")

        self._seed_diaries(student)
        prep = self._seed_conference(student)
        self._seed_events(student, prep)

        self.stdout.write(self.style.SUCCESS("デモデータの投入が完了しました。"))
        self.stdout.write("")
        self.stdout.write("ログイン情報（開発用）:")
        for email, name, role, _ in DEMO_USERS:
            self.stdout.write(f"  {email} / {DEMO_PASSWORD}  （{name}・{Role(role).label}）")

    def _seed_diaries(self, user) -> None:
        today = timezone.localdate()
        for days_ago, content, tags in DEMO_DIARIES:
            DiaryEntry.objects.get_or_create(
                user=user,
                date=today - timedelta(days=days_ago),
                defaults={"content": content, "tags": tags},
            )

    def _seed_conference(self, user) -> ConferencePrep:
        prep, created = ConferencePrep.objects.get_or_create(
            user=user,
            conference_name="言語処理学会 年次大会",
            defaults={"deadline": timezone.localdate() + timedelta(days=10)},
        )
        if created:
            ConferenceChecklistItem.objects.bulk_create(
                [
                    ConferenceChecklistItem(conference=prep, item=item, done=done)
                    for item, done in DEMO_CHECKLIST
                ]
            )
        return prep

    def _seed_events(self, user, prep: ConferencePrep) -> None:
        today = timezone.localdate()

        def at(day_offset: int, hour: int) -> datetime:
            return timezone.make_aware(datetime.combine(today + timedelta(days=day_offset), time(hour=hour)))

        demo_events = [
            # (タイトル, 開始, 終了, 種別, 学会紐付け, 研究室共通か)
            ("研究ミーティング", at(1, 10), at(1, 11), EventType.TASK, None, False),
            ("原稿の初稿を仕上げる", at(5, 9), at(5, 18), EventType.TASK, prep, False),
            ("学会原稿 提出締切", at(10, 23), None, EventType.MILESTONE, prep, False),
            ("研究室全体ゼミ", at(3, 13), at(3, 15), EventType.TASK, None, True),
        ]
        for title, start_at, end_at, event_type, conference, is_shared in demo_events:
            ScheduleEvent.objects.get_or_create(
                title=title,
                start_at=start_at,
                defaults={
                    "end_at": end_at,
                    "event_type": event_type,
                    "conference": conference,
                    "user": None if is_shared else user,
                },
            )
