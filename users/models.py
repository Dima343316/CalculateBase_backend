import uuid
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager


class UserManager(BaseUserManager):
    """Менеджер пользовательской модели."""

    def create_user(self, email, password=None, **extra_fields):
        """Создание обычного пользователя."""
        if not email:
            raise ValueError(_("Email is required"))

        email = self.normalize_email(email)
        extra_fields.setdefault("is_active", False)

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """Создание суперпользователя."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if not extra_fields.get("is_staff"):
            raise ValueError(_("Superuser must have is_staff=True."))
        if not extra_fields.get("is_superuser"):
            raise ValueError(_("Superuser must have is_superuser=True."))

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Пользователь системы (админ, менеджер, контрагент и т.д.)."""

    class Roles(models.TextChoices):
        ADMIN = "admin", _("Администратор")
        SUPERVISOR = "supervisor", _("Руководитель")
        MANAGER = "manager", _("Менеджер по продажам")
        CONTRACTOR = "contractor", _("Контрагент")

    id = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    email = models.EmailField(
        unique=True, verbose_name=_("Email (логин)")
    )
    name = models.CharField(
        max_length=255,
        verbose_name=_("ФИО / Имя"),
        blank=True,
        null=True,
    )
    role = models.CharField(
        max_length=20,
        choices=Roles.choices,
        verbose_name=_("Роль"),
        blank=True,
        null=True,
    )

    is_active = models.BooleanField(
        default=False, verbose_name=_("Активен")
    )
    is_staff = models.BooleanField(
        default=False, verbose_name=_("Доступ к админке")
    )
    is_archived = models.BooleanField(
        default=False,
        verbose_name=_("Архивный"
                       )
    )
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name=_("Дата создания")
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name=_("Дата обновления")
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name", "role"]

    objects = UserManager()

    def check_password(self, raw_password):
        if self.is_archived or not self.is_active:
            return False
        return super().check_password(raw_password)

    def __str__(self):
        return f"{self.email} ({self.get_role_display()})"


    class Meta:
        verbose_name = _("Пользователь")
        verbose_name_plural = _("Пользователи")
        ordering = ["-created_at"]



class UserInvite(models.Model):
    """Приглашение пользователя для установки пароля и активации."""

    user = models.OneToOneField(
        "User", on_delete=models.CASCADE, related_name="invite"
    )
    invite_token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    expires_at = models.DateTimeField()
    used = models.BooleanField(default=False)

    def is_expired(self):
        return self.expires_at < timezone.now()

    def __str__(self):
        return f"Приглашение для {self.user.email}"


class AuditLog(models.Model):
    ACTION_CREATE_INVITE = "create_invite"
    ACTION_CONFIRMED_INVITE = "confirmed_invite"
    ACTION_EDIT_USER = "edit_user"
    ACTION_DELETE_USER = "delete_user"
    ACTION_LOGIN = "login"
    ACTION_LOGOUT = "logout"

    ACTION_CHOICES = [
        (ACTION_CREATE_INVITE, "Создание приглашения"),
        (ACTION_CONFIRMED_INVITE, "Подтверждение приглашения"),
        (ACTION_EDIT_USER, "Редактирование пользователя"),
        (ACTION_DELETE_USER, "Удаление пользователя"),
        (ACTION_LOGIN, "Вход в систему"),
        (ACTION_LOGOUT, "Выход из системы"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="Время")
    user = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, verbose_name="Пользователь")
    action = models.CharField(max_length=50, choices=ACTION_CHOICES, verbose_name="Действие")
    module = models.CharField(max_length=50, verbose_name="Модуль")
    object_repr = models.TextField(verbose_name="Объект")
    changes = models.JSONField(blank=True, null=True, verbose_name="Изменения")

    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name=_("Дата создания")
    )
    updated_at = models.DateTimeField(
        auto_now=True, verbose_name=_("Дата обновления")
    )

    def __str__(self):
        return f"{self.timestamp:%d.%m.%Y %H:%M:%S} — {self.user} — {self.get_action_display()}"

    def get_action_display(self):
        return dict(self.ACTION_CHOICES).get(self.action, self.action)

    class Meta:
        verbose_name = _("Аудит логов")
        verbose_name_plural = _("Мониторинг логов")
        ordering = ["-created_at"]