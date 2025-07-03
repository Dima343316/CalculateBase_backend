import secrets

import requests
import string
import random

from celery.bin.upgrade import settings


def make_random_password(length=12):
    chars = string.ascii_letters + string.digits + string.punctuation
    return ''.join(random.choices(chars, k=length))


def generate_unique_memo(telegram_id: int, length: int = 12) -> str:
    """
    Генерирует уникальную мемо-фразу для пользователя.

    :param telegram_id: Telegram ID пользователя (для уникальности)
    :param length: Длина генерируемой фразы (по умолчанию 12 символов)
    :return: Уникальная мемо-фраза без префикса "memo_"
    """
    alphabet = string.ascii_letters + string.digits
    random_part = ''.join(secrets.choice(alphabet) for _ in range(length - 4))
    unique_suffix = f"{telegram_id % 10000:04d}"

    return f"{random_part}{unique_suffix}"


def get_actions(account, limit=20, sort='desc'):
    url = f'https://api.tonscan.org/api/v3/actions'
    params = {
        'account': account,
        'limit': limit,
        'sort': sort
    }

    response = requests.get(url, params=params)

    if response.status_code == 200:
        data = response.json()
        print("Ответ от API:", data)
    else:
        print("Ошибка:", response.status_code)


def send_telegram_message(telegram_id, text=None, image_path=None, sticker_id=None):

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"

    if image_path:
        with open(image_path, 'rb') as img:
            response = requests.post(f"{url}/sendPhoto", data={
                "chat_id": telegram_id,
                "caption": text or ""
            }, files={"photo": img})
    elif sticker_id:
        response = requests.post(f"{url}/sendSticker", data={
            "chat_id": telegram_id,
            "sticker": sticker_id
        })
    elif text:
        response = requests.post(f"{url}/sendMessage", data={
            "chat_id": telegram_id,
            "text": text
        })
    else:
        raise ValueError("No content to send")

    if response.status_code != 200:
        raise Exception(f"Telegram error: {response.text}")

    return response.json()


__all__=()

