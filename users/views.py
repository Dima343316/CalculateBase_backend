from django.template.loader import render_to_string
from rest_framework.permissions import AllowAny
from urllib.parse import urlencode
from .authentication import CsrfExemptSessionAuthentication
from .models import User, AuditLog
import uuid
from django.shortcuts import render, redirect, get_object_or_404
from django.views import View
from django.contrib import messages
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .mixins import AuditLogMixin
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.tokens import RefreshToken
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



class ConfirmInvitePage(View, AuditLogMixin):
    template_name = "confirm_invite_page.html"

    def get(self, request, token):
        invite = get_object_or_404(UserInvite, invite_token=token, used=False)
        if invite.is_expired():
            return render(request, "invite_expired.html")
        return render(request, self.template_name, {"token": token})

    def post(self, request, token):
        password = request.POST.get("password")
        invite = get_object_or_404(UserInvite, invite_token=token, used=False)

        if invite.is_expired():
            messages.error(request, "Срок действия токена истёк")
            return redirect("confirm_invite_page", token=token)

        if not password:
            messages.error(request, "Пароль обязателен")
            return redirect("confirm_invite_page", token=token)

        try:
            validate_password(password)
        except DjangoValidationError as e:
            messages.error(request, e.messages[0])
            return redirect("confirm_invite_page", token=token)

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
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        frontend_url = "http://localhost:3000/login-success"
        params = urlencode({
            "access": access_token,
            "refresh": refresh_token,
        })

        return redirect(f"{frontend_url}?{params}")


