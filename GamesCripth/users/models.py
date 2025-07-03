import logging
import random
import string
import uuid
from django.contrib.auth.base_user import BaseUserManager, AbstractBaseUser
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

def make_random_password(length=12):
    chars = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choices(chars, k=length))


class UserManager(BaseUserManager):
    """Менеджер пользователей, работающий с Telegram ID вместо email."""

    def create_user(self,
                    telegram_id,
                    first_name,
                    username=None,
                    last_name=None,
                    photo_url=None,
                    auth_date=None,
                    password=None,  # Добавляем параметр для пароля
                    **extra_fields
                    ):
        """Создание обычного пользователя."""
        if not telegram_id:
            raise ValueError(_('The Telegram ID field must be set.'))

        auth_date = auth_date or now()  # Устанавливаем текущее время, если не передано

        user = self.model(
            telegram_id=telegram_id,
            first_name=first_name,
            username=username,
            last_name=last_name,
            photo_url=photo_url,
            auth_date=auth_date,
            **extra_fields
        )

        if password:
            user.set_password(password)  # Хэшируем пароль

        user.save(using=self._db)
        return user

    def create_superuser(self, telegram_id, first_name, password=None, **extra_fields):
        """Создание суперпользователя с безопасным хэшированием пароля."""
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if not extra_fields.get('is_staff'):
            raise ValueError(_('Superuser must have is_staff=True.'))
        if not extra_fields.get('is_superuser'):
            raise ValueError(_('Superuser must have is_superuser=True.'))


        return self.create_user(telegram_id,
                                first_name,
                                password=password,
                                **extra_fields
                                )


class User(AbstractBaseUser, PermissionsMixin):

    last_activity = models.DateTimeField(
        null=True,
        blank=True
    )

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    telegram_id = models.BigIntegerField(
        unique=True
    )
    username = models.CharField(
        max_length=32,
        blank=True,
        null=True
    )
    first_name = models.CharField(
        max_length=64
    )
    last_name = models.CharField(
        max_length=64,
        blank=True,
        null=True
    )
    photo_url = models.URLField(
        blank=True,
        null=True
    )

    auth_date = models.DateTimeField(
        auto_now_add=True  # Заполняется автоматически при создании
    )


    memo_phrase = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    referral = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )

    is_active = models.BooleanField(default=True)

    is_staff = models.BooleanField(default=False)  # Для доступа в админку

    is_superuser = models.BooleanField(default=False)  # Для суперпользователя

    objects = UserManager()

    USERNAME_FIELD = 'telegram_id'  # Устанавливаем уникальный идентификатор пользователя
    REQUIRED_FIELDS = ['first_name']  # Параметры, которые должны быть указаны при создании пользователя

    def update_last_activity(self):
        """Обновление времени последней активности пользователя"""
        self.last_activity = now()
        self.save(update_fields=['last_activity'])
        logger.info(f"User {self.username} activity updated at {self.last_activity}")

    class Meta:
        verbose_name = "Пользователи"
        verbose_name_plural = "Пользователи"

    def __str__(self):
        return self.username or f'User {self.telegram_id}'


class Broadcast(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    message_text = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='broadcasts/', blank=True, null=True)
    sticker_id = models.CharField(max_length=128, blank=True, null=True)
    is_active = models.BooleanField(default=True)  # можно останавливать
    started_at = models.DateTimeField(blank=True, null=True)
    finished_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Broadcast #{self.pk} — {'Active' if self.is_active else 'Stopped'}"


class BroadcastLog(models.Model):
    broadcast = models.ForeignKey(Broadcast, on_delete=models.CASCADE, related_name='logs')
    user = models.ForeignKey('users.User', on_delete=models.CASCADE)
    sent = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ('broadcast', 'user')


__all__ = ()
