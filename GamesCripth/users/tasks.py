# app/tasks.py
import time

from celery import shared_task
from django.utils.timezone import now

from .config import RATE_LIMIT_DELAY, BATCH_SIZE
from .models import Broadcast, BroadcastLog
from users.models import User
import logging
from users.utils import send_telegram_message

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def start_broadcast(self, broadcast_id):
    broadcast = Broadcast.objects.get(pk=broadcast_id)
    broadcast.started_at = now()
    broadcast.save(update_fields=['started_at'])

    users = User.objects.filter(is_active=True).iterator(chunk_size=BATCH_SIZE)

    for user in users:
        if not Broadcast.objects.filter(pk=broadcast_id, is_active=True).exists():
            logger.info(f"Broadcast #{broadcast_id} stopped manually.")
            break

        try:
            # Проверка дубликатов
            if BroadcastLog.objects.filter(broadcast=broadcast, user=user).exists():
                continue

            message = send_telegram_message(
                telegram_id=user.telegram_id,
                text=broadcast.message_text,
                image_path=broadcast.image.path if broadcast.image else None,
                sticker_id=broadcast.sticker_id
            )

            BroadcastLog.objects.create(
                broadcast=broadcast,
                user=user,
                sent=True,
                sent_at=now()
            )
        except Exception as e:
            logger.warning(f"Error sending to {user.telegram_id}: {str(e)}")
            BroadcastLog.objects.create(
                broadcast=broadcast,
                user=user,
                sent=False,
                error_message=str(e)
            )

        time.sleep(RATE_LIMIT_DELAY)

    broadcast.finished_at = now()
    broadcast.save(update_fields=['finished_at'])