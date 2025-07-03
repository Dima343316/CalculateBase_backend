from django.contrib.auth.password_validation import validate_password
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken
from django.core.exceptions import ValidationError as DjangoValidationError

from .authentication import CsrfExemptSessionAuthentication
from .mixins import AuditLogMixin
from .models import User, UserInvite, AuditLog
import uuid

from .models import UserInvite
from .tasks import send_email_celery  # импортируем нашу задачу


class SendInviteView(APIView):
    def post(self, request):
        email = request.data.get("email")
        name = request.data.get("name")
        role = request.data.get("role")

        if not all([email, name, role]):
            return Response({"error": "Недостаточно данных"}, status=400)

        user = User.objects.create(
            email=email,
            name=name,
            role=role,
            is_active=False,
        )

        invite = UserInvite.objects.create(
            user=user,
            invite_token=uuid.uuid4(),
            expires_at=timezone.now() + timezone.timedelta(days=3),
        )

        invite_link = f"https://your-domain.com/invite/confirm/{invite.invite_token}"

        # HTML-шаблон + текст fallback
        html_content = render_to_string("emails/invite_user.html", {
            "name": name,
            "invite_link": invite_link
        })

        text_content = f"""Здравствуйте, {name}!

Вас пригласили в систему. Пройдите по ссылке для регистрации:
{invite_link}

Если вы не ожидали это письмо — проигнорируйте его."""

        email_data = {
            "subject": "Приглашение в систему",
            "body": text_content,
            "from_email": "admin@your-domain.com",
            "to": [email],
            "alternatives": [(html_content, "text/html")]
        }

        send_email_celery.delay([email_data])
        return Response({"status": "invite_sent"}, status=201)




class ConfirmInviteView(APIView, AuditLogMixin):
    authentication_classes = [CsrfExemptSessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request, token):
        password = request.data.get("password")

        if not password:
            return Response({"error": "Пароль обязателен"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(password)
        except DjangoValidationError as e:
            return Response({"error": e.messages}, status=status.HTTP_400_BAD_REQUEST)

        invite = get_object_or_404(UserInvite, invite_token=token, used=False)

        if invite.is_expired():
            return Response({"error": "Срок действия токена истёк"}, status=status.HTTP_400_BAD_REQUEST)

        user = invite.user
        user.set_password(password)
        user.is_active = True
        user.save()

        invite.used = True
        invite.save()

        self.log_action(
            user=user,
            action=AuditLog.ACTION_CONFIRMED_INVITE,
            module="users",
            obj=user,
            changes={"set_password": True, "is_active": True}
        )

        refresh = RefreshToken.for_user(user)

        return Response({
            "status": "user_activated",
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": str(user.id),
                "email": user.email,
                "name": user.name,
                "role": user.role,
            }
        }, status=status.HTTP_200_OK)