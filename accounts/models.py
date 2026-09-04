"""ユーザー・認証（詳細設計書 2.1 User）。"""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


class Role(models.TextChoices):
    FACULTY = "faculty", "教員"
    STUDENT = "student", "学生"


class UserManager(BaseUserManager):
    """メールアドレスをログインIDとするユーザーマネージャ。"""

    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("メールアドレスは必須です。")
        extra_fields.setdefault("role", Role.STUDENT)
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", Role.FACULTY)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("スーパーユーザーは is_staff=True である必要があります。")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("スーパーユーザーは is_superuser=True である必要があります。")
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("メールアドレス", unique=True)
    name = models.CharField("表示名", max_length=50)
    role = models.CharField("役割", max_length=10, choices=Role.choices, default=Role.STUDENT)
    joined_at = models.DateTimeField("登録日時", auto_now_add=True)
    is_active = models.BooleanField("有効", default=True)
    is_staff = models.BooleanField("管理画面利用可", default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        verbose_name = "ユーザー"
        verbose_name_plural = "ユーザー"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name}（{self.get_role_display()}）"

    def get_short_name(self) -> str:
        return self.name

    def get_full_name(self) -> str:
        return self.name

    @property
    def is_faculty(self) -> bool:
        """教員ロールか（承認系機能の権限判定に使用）。"""
        return self.role == Role.FACULTY
