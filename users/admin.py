from django.contrib.admin import DateFieldListFilter
from django.utils import timezone
from django.contrib import admin
from django.conf import settings
from django.contrib import messages
from django.utils.html import format_html

from .mixins import AuditLogMixin
from .models import User, UserInvite, AuditLog
from .tasks import send_email_celery
from django.template.loader import render_to_string
import uuid
from .forms import SendInviteAdminForm


@admin.register(User)
class UserAdmin(admin.ModelAdmin, AuditLogMixin):
    add_form = SendInviteAdminForm

    list_display = (
        "email",
        "name",
        "role",
        "confirmed_display",
        "active_display",
        "created_at",
        "updated_at"
    )
    search_fields = ("email", "name")
    ordering = ("-created_at",)
    readonly_fields = (
        "created_at",
        "updated_at",
        "last_login"
    )

    list_filter = (
        "role",
        "is_active",
        "is_archived",
        ("updated_at", DateFieldListFilter),
    )

    def confirmed_display(self, obj):
        if obj.is_active:
            return format_html('<span style="color: green;">✔ Подтверждён</span>')
        return format_html('<span style="color: gray;">✖ Не подтверждён</span>')
    confirmed_display.short_description = "Подтверждение"

    def active_display(self, obj):
        if obj.is_archived:
            return format_html('<span style="color: gray;">📁 Архивный</span>')
        return format_html('<span style="color: green;">🟢 Активный</span>')
    active_display.short_description = "Статус"

    def get_fieldsets(self, request, obj=None):
        if not obj:
            return [(None, {'fields': ('email', 'name', 'role')})]
        return super().get_fieldsets(request, obj)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.is_active = False
            obj.set_unusable_password()
            obj.save()

            invite = UserInvite.objects.create(
                user=obj,
                invite_token=uuid.uuid4(),
                expires_at=timezone.now() + timezone.timedelta(days=3)
            )

            invite_link = f"http://localhost:8000/users/invite/confirm/{invite.invite_token}/"
            html_content = render_to_string("emails/invite_user.html", {
                "name": obj.name or "пользователь",
                "invite_link": invite_link
            })

            text_content = f"""Здравствуйте!\n\nВас пригласили в систему. Пройдите по ссылке для регистрации:\n{invite_link}\n\nЕсли вы не ожидали это письмо — проигнорируйте его."""

            email_data = {
                "subject": "Приглашение в систему",
                "body": text_content,
                "from_email": settings.EMAIL_HOST_USER,
                "to": [obj.email],
                "alternatives": [(html_content, "text/html")]
            }

            send_email_celery.delay([email_data])
            messages.success(request, f"Приглашение отправлено на {obj.email}")

            self.log_action(
                user=request.user,
                action=AuditLog.ACTION_CREATE_INVITE,
                module="users",
                obj=obj,
                changes={"email": obj.email, "role": obj.role}
            )
        else:
            super().save_model(request, obj, form, change)

            self.log_action(
                user=request.user,
                action=AuditLog.ACTION_EDIT_USER,
                module="users",
                obj=obj,
                changes={field: form.cleaned_data.get(field) for field in form.changed_data}
            )

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user_display", "module", "action_display")
    list_filter = ("module", "action", "timestamp")
    search_fields = ("user__email", "object_repr", "module")
    ordering = ("-timestamp",)
    readonly_fields = [f.name for f in AuditLog._meta.fields]
    list_per_page = 25

    def user_display(self, obj):
        return obj.user.email if obj.user else "Система"
    user_display.short_description = "Пользователь"

    def action_display(self, obj):
        return dict(AuditLog.ACTION_CHOICES).get(obj.action, obj.action)
    action_display.short_description = "Действие"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False