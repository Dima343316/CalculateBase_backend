from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.message import EmailMultiAlternatives
from .tasks import send_email_celery


class CeleryEmail(BaseEmailBackend):
    def send_messages(self, email_messages: list[EmailMultiAlternatives]):
        emails = []
        for message in email_messages:
            try:
                message.render()
            except Exception as error:
                print(f"Ошибка рендера email: {error}")

            data = {
                "subject": message.subject,
                "body": message.body,
                "from_email": message.from_email,
                "to": message.to,
                "bcc": message.bcc,
                "attachments": message.attachments,
                "alternatives": message.alternatives,
                "cc": message.cc,
                "reply_to": message.reply_to,
                "headers": message.extra_headers,
            }
            emails.append(data)
        send_email_celery.delay(emails)

__all__ = ()
