import hashlib

import logging
import requests
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils.translation import gettext_lazy as _
from django.views.generic import TemplateView
from django_telegram_login.widgets.constants import (SMALL,
                                                     LARGE,
                                                     DISABLE_USER_PHOTO
                                                     )
from django_telegram_login.widgets.generator import (
    create_redirect_login_widget,
)
from django_telegram_login.authentication import verify_telegram_authentication
from django.views import View
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken
from games.models import User
from users.utils import generate_unique_memo
from django.http import HttpRequest

BOT_NAME = settings.TELEGRAM_BOT_NAME
BOT_TOKEN = settings.TELEGRAM_BOT_TOKEN
REDIRECT_URL = settings.TELEGRAM_LOGIN_REDIRECT_URL


logger = logging.getLogger(__name__)

class TelegramAuthView(View):
    def get(self, request):
        if 'hash' not in request.GET:
            logger.warning("Ошибка аутентификации: отсутствуют данные Telegram (hash).")
            return JsonResponse({'error': 'Данные Telegram отсутствуют в запросе.'}, status=400)

        try:
            user_data = verify_telegram_authentication(
                bot_token=settings.TELEGRAM_BOT_TOKEN,
                request_data=request.GET
            )
        except Exception as e:
            logger.error(f"Ошибка при верификации Telegram: {e}")
            return JsonResponse({'error': 'Ошибка при обработке данных Telegram.'}, status=500)

        telegram_id = int(user_data['id'])
        try:
            with transaction.atomic():
                user, created = User.objects.update_or_create(
                    telegram_id=telegram_id,
                    defaults={
                        'username': user_data.get('username', ''),
                        'first_name': user_data['first_name'],
                        'last_name': user_data.get('last_name', ''),
                        'photo_url': user_data.get('photo_url', ''),
                    }
                )

                if created or not user.memo_phrase:
                    user.memo_phrase = user.telegram_id
                    user.save()
                    logger.info(f"✅ Сгенерирована новая мемо-фраза для {user.telegram_id}: {user.memo_phrase}")

                self.send_telegram_message(user.telegram_id, (
                    f"✅ Добро пожаловать, {user.first_name}!\n\n"
                    f"📌 Ваша уникальная мемо-фраза: {user.memo_phrase}\n\n"
                    f"⚠️ Используйте её при отправке платежей!"
                ))

                # Создание JWT токенов
                refresh = RefreshToken.for_user(user)
                access = str(refresh.access_token)

                # Редирект на страницу с токеном в URL
                return redirect(f"https://localhost:5173/auth?access={access}&refresh={str(refresh)}")

        except Exception as e:
            logger.error(f"❌ Ошибка при обновлении пользователя: {e}")
            return JsonResponse({'error': 'Ошибка при обновлении пользователя.'}, status=500)

    def send_telegram_message(self, telegram_id, message):
        """Отправка сообщения в Telegram через Bot API"""
        url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': telegram_id,
            'text': message,
            'parse_mode': 'Markdown'
        }

        try:
            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"✅ Сообщение отправлено пользователю {telegram_id}")
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Ошибка при отправке сообщения Telegram {telegram_id}: {str(e)}")


class MemoPhraseView(APIView):
    """
    Получение memo-фразы пользователя для пополнения баланса.
    Требуется авторизация.
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        user = request.user

        if not user.memo_phrase:
            return Response(
                {"detail": _("Memo phrase not set for this user.")},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response(
            {"memo_phrase": user.memo_phrase},
            status=status.HTTP_200_OK
        )


def redirect_view(request: HttpRequest):
    referral_id = request.GET.get('referral_id')
    user_id = request.user.id if request.user.is_authenticated else 'anonymous'

    # Получаем актуальный домен и протокол
    scheme = 'https' if request.is_secure() else 'http'
    current_domain = request.get_host()  # вернёт pingapp.tech:8443
    base_url = f"{scheme}://{current_domain}"

    if referral_id:
        hash_input = f"{user_id}{referral_id}"
        referral_hash = hashlib.md5(hash_input.encode()).hexdigest()
        redirect_url = f'{base_url}/users/telegram/auth/?referral_hash={referral_hash}'
    else:
        redirect_url = f'https://gamescripth.share.zrok.io/users/telegram/auth/'

    widget_html = create_redirect_login_widget(
        redirect_url=redirect_url,
        bot_name=BOT_NAME,
        size=SMALL,
        user_photo=DISABLE_USER_PHOTO,
    )

    return render(request, 'redirect.html', {'telegram_login_widget': widget_html})


def check_telegram_user(request):
    """
    Проверяет, авторизован ли пользователь через Telegram.
    """
    telegram_user_id = request.session.get('telegram_user_id')

    if telegram_user_id:
        try:
            user = User.objects.get(telegram_id=telegram_user_id)
            return HttpResponse(f"Пользователь {user.username} аутентифицирован.")
        except User.DoesNotExist:
            return HttpResponse("Пользователь не найден в базе данных.", status=404)
    else:
        return HttpResponse("Пользователь не авторизован.", status=403)


class AuthSuccessRedirectView(TemplateView):
    template_name = "auth/success_redirect.html"

__all__=()
