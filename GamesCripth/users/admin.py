from django.contrib import admin
from django.contrib.sessions.models import Session
from django.utils import timezone
from django.utils.html import format_html

from .models import User, Broadcast, BroadcastLog


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Настройки для отображения и управления пользователями в админке."""

    list_display = (
        "id_display", "telegram_id_display", "username_display", "first_name_display",
        "last_name_display", "auth_date_display", "memo_phrase_display"
    )
    list_filter = ("auth_date",)  # Фильтр по дате авторизации
    search_fields = (
        "username",
        "first_name",
        "last_name",
        "telegram_id"
    )  # Поля для поиска
    ordering = ("-auth_date",)  # Сортировка по дате авторизации
    readonly_fields = (
        "id",
        "telegram_id",
        "auth_date"
    )  # Поля только для чтения
    actions = ['reset_user_password']  # Пример действия для сброса пароля

    @admin.display(description="ID пользователя")
    def id_display(self, obj):
        return obj.id

    @admin.display(description="Telegram ID")
    def telegram_id_display(self, obj):
        return obj.telegram_id

    @admin.display(description="Имя пользователя")
    def username_display(self, obj):
        return obj.username

    @admin.display(description="Имя")
    def first_name_display(self, obj):
        return obj.first_name

    @admin.display(description="Фамилия")
    def last_name_display(self, obj):
        return obj.last_name

    @admin.display(description="Дата авторизации")
    def auth_date_display(self, obj):
        return obj.auth_date

    @admin.display(description="Мнемоническая фраза")
    def memo_phrase_display(self, obj):
        return obj.memo_phrase

    @admin.action(description="Сбросить пароль пользователя")
    def reset_user_password(self, request, queryset):
        for user in queryset:
            # Здесь можно добавить логику для сброса пароля
            # Пример: user.set_password('новый_пароль')
            self.message_user(request, f"Пароль для пользователя {user.username} сброшен.")
            # Не забудьте сохранить изменения
            user.save()

class SessionAdmin(admin.ModelAdmin):
    list_display = ('session_key', 'get_user', 'expire_date')
    readonly_fields = ('session_key', 'get_user', 'expire_date')

    def get_user(self, obj):
        """Получаем пользователя из данных сессии."""
        session_data = obj.get_decoded()  # Получаем расшифрованные данные сессии
        telegram_id = session_data.get('telegram_id')

        if telegram_id:
            try:
                user = User.objects.get(telegram_id=telegram_id)
                return format_html(f'<a href="/admin/users/user/{user.id}/">{user.username or user.telegram_id}</a>')
            except User.DoesNotExist:
                return "Не найден"
        return "Не указан"

    get_user.short_description = "Пользователь"

admin.site.register(Session, SessionAdmin)

@admin.register(Broadcast)
class BroadcastAdmin(admin.ModelAdmin):
    list_display = ['id', 'created_at', 'is_active', 'started_at', 'finished_at']
    actions = ['start_broadcast_now', 'stop_broadcast']

    def start_broadcast_now(self, request, queryset):
        for broadcast in queryset:
            start_broadcast.delay(broadcast.id)

    def stop_broadcast(self, request, queryset):
        queryset.update(is_active=False)

    start_broadcast_now.short_description = "Начать рассылку"
    stop_broadcast.short_description = "Остановить рассылку"


@admin.register(BroadcastLog)
class BroadcastLogAdmin(admin.ModelAdmin):
    list_display = ['broadcast', 'user', 'sent', 'sent_at', 'error_message']
    list_filter = ['sent']