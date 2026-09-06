"""出張費申請（フォームとメール送信）のテスト。"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Role
from office.models import TravelExpenseRequest
from research.models import ConferencePrep

User = get_user_model()


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    TRAVEL_EXPENSE_RECIPIENTS=["office@example.ac.jp"],
    DEFAULT_FROM_EMAIL="labops@example.ac.jp",
)
class TravelExpenseRequestTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(email="student@example.com", password="pw12345!", name="申請者")
        cls.teacher = User.objects.create_user(
            email="teacher@example.com", password="pw12345!", name="指導教員", role=Role.FACULTY
        )

    def setUp(self):
        self.client.force_login(self.user)
        self.url = reverse("office:travel_expense_list")
        self.today = timezone.localdate()

    def _post(self, **overrides):
        data = {
            "destination": "京都大学",
            "purpose": "言語処理学会 年次大会での口頭発表",
            "amount": "45000",
            "travel_start": self.today.isoformat(),
            "travel_end": (self.today + timedelta(days=2)).isoformat(),
        }
        data.update(overrides)
        return self.client.post(self.url, data)

    # --- 申請 ---

    def test_requires_login(self):
        self.client.logout()
        self.assertRedirects(self.client.get(self.url), f"{reverse('accounts:login')}?next={self.url}")

    def test_request_is_saved_with_the_applicant(self):
        response = self._post()
        self.assertRedirects(response, self.url)

        expense = TravelExpenseRequest.objects.get()
        self.assertEqual(expense.user, self.user)
        self.assertEqual(expense.destination, "京都大学")
        self.assertEqual(int(expense.amount), 45000)
        self.assertEqual(expense.status, "pending")

    def test_amount_must_be_positive(self):
        response = self._post(amount="0")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(TravelExpenseRequest.objects.exists())

    def test_end_date_must_not_precede_start(self):
        response = self._post(travel_end=(self.today - timedelta(days=1)).isoformat())
        self.assertEqual(response.status_code, 400)
        self.assertFalse(TravelExpenseRequest.objects.exists())

    def test_same_day_trip_is_allowed(self):
        response = self._post(travel_end=self.today.isoformat())
        self.assertRedirects(response, self.url)
        self.assertTrue(TravelExpenseRequest.objects.exists())

    def test_list_shows_only_own_requests(self):
        self._post()
        TravelExpenseRequest.objects.create(
            user=self.teacher,
            destination="他人の出張",
            purpose="別件",
            amount=1000,
            travel_start=self.today,
            travel_end=self.today,
        )
        response = self.client.get(self.url)
        self.assertContains(response, "京都大学")
        self.assertNotContains(response, "他人の出張")

    # --- メール ---

    def test_mail_is_sent_to_configured_recipients(self):
        self._post()
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["office@example.ac.jp"])
        self.assertEqual(message.from_email, "labops@example.ac.jp")

    def test_mail_subject_identifies_the_applicant_and_destination(self):
        self._post()
        self.assertEqual(mail.outbox[0].subject, "[LabOps] 出張費申請: 申請者 / 京都大学")

    def test_mail_body_contains_the_submitted_values(self):
        self._post()
        body = mail.outbox[0].body
        self.assertIn("申請者", body)
        self.assertIn("京都大学", body)
        self.assertIn("45,000 円", body)
        self.assertIn("言語処理学会 年次大会での口頭発表", body)
        self.assertIn(str(self.today), body)

    def test_reply_goes_back_to_the_applicant(self):
        self._post()
        self.assertEqual(mail.outbox[0].reply_to, ["student@example.com"])

    @override_settings(TRAVEL_EXPENSE_RECIPIENTS=[])
    def test_falls_back_to_faculty_addresses(self):
        """送信先の設定がなければ、教員ロールのメールアドレスへ送る。"""
        self._post()
        self.assertEqual(mail.outbox[0].to, ["teacher@example.com"])

    @override_settings(TRAVEL_EXPENSE_RECIPIENTS=[])
    def test_saved_even_when_there_is_no_recipient(self):
        """送信先が1つもなくても、申請は保存して画面で知らせる。"""
        self.teacher.delete()
        response = self._post()
        self.assertRedirects(response, self.url)
        self.assertTrue(TravelExpenseRequest.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

        messages = [str(m) for m in response.wsgi_request._messages]
        self.assertTrue(any("送信できませんでした" in m for m in messages))

    def test_no_mail_when_the_form_is_invalid(self):
        self._post(amount="0")
        self.assertEqual(len(mail.outbox), 0)

    # --- 学会準備からの導線 ---

    def test_conference_prefills_the_form(self):
        prep = ConferencePrep.objects.create(
            conference_name="言語処理学会 年次大会", deadline=self.today, user=self.user
        )
        response = self.client.get(self.url, {"conference": prep.pk})
        form = response.context["form"]
        self.assertEqual(form["destination"].value(), "言語処理学会 年次大会")
        self.assertIn("言語処理学会 年次大会", form["purpose"].value())

    def test_other_members_conference_is_not_used(self):
        prep = ConferencePrep.objects.create(
            conference_name="他人の学会", deadline=self.today, user=self.teacher
        )
        response = self.client.get(self.url, {"conference": prep.pk})
        self.assertIsNone(response.context["form"]["destination"].value())

    def test_invalid_conference_parameter_is_ignored(self):
        response = self.client.get(self.url, {"conference": "abc"})
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["form"]["destination"].value())

    def test_conference_page_links_to_the_form(self):
        ConferencePrep.objects.create(
            conference_name="言語処理学会 年次大会", deadline=self.today, user=self.user
        )
        response = self.client.get(reverse("research:conference_list"))
        self.assertContains(response, reverse("office:travel_expense_list"))
        self.assertContains(response, "出張費")
