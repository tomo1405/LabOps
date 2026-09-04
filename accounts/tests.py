"""ユーザーモデル・ログインのテスト（詳細設計書 2.1 / 3.1）。"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Role

User = get_user_model()


class UserModelTests(TestCase):
    def test_create_user_defaults_to_student(self):
        user = User.objects.create_user(email="s@example.com", password="pw12345!", name="学生")
        self.assertEqual(user.role, Role.STUDENT)
        self.assertFalse(user.is_faculty)
        self.assertTrue(user.check_password("pw12345!"))

    def test_create_superuser_is_faculty(self):
        admin = User.objects.create_superuser(email="t@example.com", password="pw12345!", name="教員")
        self.assertTrue(admin.is_faculty)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)

    def test_email_is_required(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(email="", password="pw12345!", name="名無し")

    def test_email_is_normalized(self):
        user = User.objects.create_user(email="A@EXAMPLE.COM", password="pw12345!", name="学生")
        self.assertEqual(user.email, "A@example.com")


class LoginViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            email="member@example.com", password="pw12345!", name="研究室メンバー"
        )

    def test_login_with_email_succeeds(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "member@example.com", "password": "pw12345!"}
        )
        self.assertRedirects(response, reverse("research:dashboard"))

    def test_login_with_wrong_password_fails(self):
        response = self.client.post(
            reverse("accounts:login"), {"username": "member@example.com", "password": "wrong"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_logout_redirects_to_login(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("accounts:login"))
