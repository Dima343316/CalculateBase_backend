import os

from celery import Celery
from celery.schedules import crontab,schedule

from django.conf import settings


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "GamesCripth.settings")

app = Celery("GamesCripth")

app.config_from_object(
    "django.conf:settings",
    namespace="CELERY"
)


app.conf.beat_schedule = {
    "auto-start-games-every-1-minute": {
        "task": "games.tasks.auto_start_games",
        "schedule": crontab(minute="*"),  # запуск каждую минуту (это ок)
    },
    "finish-expired-game-sessions-every-10-seconds": {
        "task": "games.tasks.finish_expired_game_sessions",
        "schedule": schedule(10.0),  # запуск каждые 10 секунд!
    },
}


app.autodiscover_tasks()
