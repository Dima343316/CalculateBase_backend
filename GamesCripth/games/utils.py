from math import modf
import requests
from django.conf import settings
import logging

from GamesCripth.settings import TELEGRAM_BOT_TOKEN

logger = logging.getLogger(__name__)


TELEGRAM_API_URL = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"

def is_integer(decimal_value):
    return modf(decimal_value)[0] == 0

def send_telegram_message(telegram_id, message):
    """Отправка сообщения пользователю через Telegram Bot API с обработкой ошибок."""
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


def send_telegram_messages_views(chat_id, message):
    """Функция отправки сообщения в Telegram"""
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(TELEGRAM_API_URL, json=data)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Ошибка отправки сообщения в Telegram: {e}")


def send_telegram_message_admin(username_or_chat_id: str, message: str):
    """
    Отправляет сообщение в Telegram пользователю (@username) или чату (chat_id).

    :param username_or_chat_id: Telegram username (в формате @username) или ID чата (число).
    :param message: Текст сообщения.
    """
    try:
        if username_or_chat_id.startswith("@"):
            chat_id = get_chat_id_by_username(username_or_chat_id)
            if not chat_id:
                logger.error(f"Failed to find chat ID for {username_or_chat_id}")
                return False
        else:
            chat_id = username_or_chat_id

        response = requests.post(TELEGRAM_API_URL, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        })

        if response.status_code == 200:
            logger.info(f"Message sent to {username_or_chat_id}: {message}")
            return True
        else:
            logger.error(f"Failed to send message: {response.text}")
            return False

    except Exception as e:
        logger.exception(f"Error sending Telegram message: {e}")
        return False


def get_chat_id_by_username(username: str):
    """
    Получает chat_id пользователя по его username через Bot API.

    ⚠️ Внимание! Этот метод работает, только если пользователь ранее писал боту.

    :param username: Telegram username в формате @username
    :return: chat_id пользователя или None
    """
    try:
        response = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates")
        print(response.json())
        if response.status_code == 200:
            updates = response.json().get("result", [])
            for update in updates:
                message = update.get("message", {})
                user = message.get("from", {})
                if user.get("username") and f"@{user['username']}" == username:
                    return user.get("id")
        return None
    except Exception as e:
        logger.exception(f"Error fetching chat ID for {username}: {e}")
        return None

__all__=()
