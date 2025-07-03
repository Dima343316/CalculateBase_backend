from celery import shared_task
from django.core.mail import get_connection
from django.core.mail.message import EmailMultiAlternatives
import logging
import environ
logger = logging.getLogger(__name__)

env = environ.Env()
environ.Env.read_env()

@shared_task()
def send_email_celery(emails):
    con = get_connection("django.core.mail.backends.smtp.EmailBackend")
    emails = [EmailMultiAlternatives(**i) for i in emails]
    con.send_messages(emails)

__all__=()
