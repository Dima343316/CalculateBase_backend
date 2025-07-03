from datetime import timedelta
from django.urls import reverse, path, reverse_lazy
from django.http import HttpResponse
from django.shortcuts import render
from django.utils.html import format_html

from games.models import (
    Game,
    GameSession,
    CoinBetLimit,
    WithdrawalRequest
)
from django.contrib import admin
from django.utils.timezone import now

from users.models import User
from .forms import GameForm
from .models import (
    Coin,
    UserBalance,
    GameSessionWinningCell,
    UserGameSession,
    TransactionHistory
)



class CoinAdmin(admin.ModelAdmin):
    list_display = (
        'name_display', 'symbol_display', 'coin_type_display',
        'created_at_display', 'updated_at_display', 'qr_code_display'
    )
    search_fields = ('name', 'symbol', 'coin_type')
    ordering = ('-created_at',)
    readonly_fields = ('created_at', 'updated_at')

    def name_display(self, obj):
        return obj.name
    name_display.short_description = "Название"

    def symbol_display(self, obj):
        return obj.symbol
    symbol_display.short_description = "Символ"

    def coin_type_display(self, obj):
        return obj.coin_type
    coin_type_display.short_description = "Тип монеты"

    def created_at_display(self, obj):
        return obj.created_at
    created_at_display.short_description = "Дата создания"

    def updated_at_display(self, obj):
        return obj.updated_at
    updated_at_display.short_description = "Дата обновления"

    def qr_code_display(self, obj):
        if obj.qr_code_image:
            return format_html('<img src="{}" width="50" height="50" />', obj.qr_code_image.url)
        elif obj.qr_code_url:
            return format_html('<img src="{}" width="50" height="50" />', obj.qr_code_url)
        return "Нет QR-кода"
    qr_code_display.allow_tags = True
    qr_code_display.short_description = "QR-код"

    def save_model(self, request, obj, form, change):
        if Coin.objects.filter(symbol=obj.symbol).exists() and not change:
            raise ValueError("Этот символ уже существует!")
        super().save_model(request, obj, form, change)

class UserBalanceAdmin(admin.ModelAdmin):
    list_display = (
        'user_display',
        'coin_display',
        'amount_display',
        'locked_amount_display',
        'created_at_display',
        'updated_at_display'
    )
    list_filter = ('coin',)
    search_fields = ('user__username', 'coin__symbol')
    readonly_fields = ('created_at', 'updated_at')

    def save_model(self, request, obj, form, change):
        if obj.amount < 0:
            raise ValueError("Баланс не может быть отрицательным!")
        super().save_model(request, obj, form, change)

    # Русские подписи
    def user_display(self, obj):
        return obj.user.username
    user_display.short_description = 'Пользователь'

    def coin_display(self, obj):
        return obj.coin.symbol
    coin_display.short_description = 'Монета'

    def amount_display(self, obj):
        return obj.amount
    amount_display.short_description = 'Баланс'

    def locked_amount_display(self, obj):
        return obj.locked_amount
    locked_amount_display.short_description = 'Заблокировано'

    def created_at_display(self, obj):
        return obj.created_at.strftime('%Y-%m-%d %H:%M:%S')
    created_at_display.short_description = 'Создано'

    def updated_at_display(self, obj):
        return obj.updated_at.strftime('%Y-%m-%d %H:%M:%S')
    updated_at_display.short_description = 'Обновлено'


class GameSessionWinningCellAdmin(admin.ModelAdmin):
    list_display = (
        'game_session_display',
        'cell_number_display',
        'created_at_display',
    )
    list_filter = ('game_session',)
    search_fields = ('game_session__id', 'cell_number')
    readonly_fields = ('created_at',)

    def game_session_display(self, obj):
        return f"Сессия #{obj.game_session.id}"
    game_session_display.short_description = 'Игровая сессия'

    def cell_number_display(self, obj):
        return obj.cell_number
    cell_number_display.short_description = 'Выигрышная ячейка'

    def created_at_display(self, obj):
        return obj.created_at.strftime('%Y-%m-%d %H:%M:%S')
    created_at_display.short_description = 'Создано'

class UserGameSessionAdmin(admin.ModelAdmin):
    list_display = (
        'user_display',
        'game_session_display',
        'status_display',
        'bet_amount_display',
        'result_display',
        'winning_amount_display',
        'created_at'
    )
    list_filter = ('status', 'game_session__game__name')
    search_fields = ('user__username', 'game_session__game__name')
    readonly_fields = ('created_at', 'updated_at')

    def user_display(self, obj):
        return obj.user.username
    user_display.short_description = 'Пользователь'

    def game_session_display(self, obj):
        return f"Сессия #{obj.game_session.id} ({obj.game_session.game.name})"
    game_session_display.short_description = 'Игровая сессия'

    def status_display(self, obj):
        statuses = {
            'active': 'Активна',
            'finished': 'Завершена',
            'cancelled': 'Отменена'
        }
        return statuses.get(obj.status, obj.status)
    status_display.short_description = 'Статус'

    def bet_amount_display(self, obj):
        coins = obj.game_session.game.supported_coins.all()
        coin_symbols = ", ".join([c.symbol for c in coins])
        return f"{obj.bet_amount} ({coin_symbols}) ставка" if coin_symbols else f"{obj.bet_amount} ставка"

    def result_display(self, obj):
        return obj.result if obj.result is not None else "—"
    result_display.short_description = 'Результат'

    def winning_amount_display(self, obj):
        return f"{obj.winning_amount} {obj.game_session.game.coin.symbol}" if obj.winning_amount else "0"
    winning_amount_display.short_description = 'Выигрыш'

    def save_model(self, request, obj, form, change):
        if obj.status == 'finished' and obj.result is None:
            raise ValueError("Для завершённой сессии должен быть указан результат!")
        super().save_model(request, obj, form, change)

    def get_online_players_count(self):
        now_time = now()
        return UserGameSession.objects.filter(
            game_session__status='active',
            game_session__end_time__gte=now_time,
            status='active'
        ).values('user_id').distinct().count()

    def changelist_view(self, request, extra_context=None):
        online_count = self.get_online_players_count()
        extra_context = extra_context or {}
        extra_context['online_players_count'] = online_count
        return super().changelist_view(request, extra_context=extra_context)


class TransactionHistoryAdmin(admin.ModelAdmin):
    list_display = (
        'user_display',
        'coin_display',
        'amount_display',
        'type_display',
        'subtype',
        'related_game_session_display',
        'related_user_game_session_display',
        'created_at',
        'trace_id',
        'memo_phrase',
    )
    list_filter = ('type', 'subtype', 'created_at')
    search_fields = ('user_balance__user__username', 'type', 'subtype')
    readonly_fields = ('created_at',)

    def user_display(self, obj):
        return obj.user_balance.user.username
    user_display.short_description = "Пользователь"

    def coin_display(self, obj):
        return obj.user_balance.coin.symbol
    coin_display.short_description = "Монета"

    def amount_display(self, obj):
        return f"{obj.amount} {obj.user_balance.coin.symbol}"
    amount_display.short_description = "Сумма"

    def type_display(self, obj):
        types = {
            'arrival': 'Поступление',
            'withdrawal': 'Вывод',
            'transfer': 'Перевод'
        }
        return types.get(obj.type, obj.type)
    type_display.short_description = "Тип транзакции"

    def related_game_session_display(self, obj):
        if obj.related_game_session:
            return f"Сессия #{obj.related_game_session.id}"
        return "-"
    related_game_session_display.short_description = "Игровая сессия"

    def related_user_game_session_display(self, obj):
        if obj.related_user_game_session:
            return f"Сессия игрока #{obj.related_user_game_session.id}"
        return "-"
    related_user_game_session_display.short_description = "Сессия игрока"

    def save_model(self, request, obj, form, change):
        if obj.type not in ['arrival', 'withdrawal', 'transfer']:
            raise ValueError("Некорректный тип транзакции!")
        super().save_model(request, obj, form, change)


class CoinBetLimitAdmin(admin.ModelAdmin):
    list_display = ('coin_display', 'allowed_bets_display')
    search_fields = ('coin__name',)
    list_filter = ('coin',)

    def coin_display(self, obj):
        return obj.coin.name
    coin_display.short_description = "Монета"

    def allowed_bets_display(self, obj):
        return ", ".join(str(bet) for bet in obj.allowed_bets)
    allowed_bets_display.short_description = "Допустимые ставки"


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):

    list_display = (
        "name_display", "status_display", "cell_count_display", "bet_amount_display",
        "game_time_display", "auto_start_interval_display",
        "show_online_players_link", "show_online_players_list",
    )
    list_filter = ("status",)
    search_fields = ("name",)
    actions = ["start_game_session", 'remove_coins']

    @admin.display(description="Название")
    def name_display(self, obj):
        return obj.name

    @admin.display(description="Статус")
    def status_display(self, obj):
        return obj.status

    @admin.display(description="Количество ячеек")
    def cell_count_display(self, obj):
        return obj.cell_count

    @admin.display(description="Ставка")
    def bet_amount_display(self, obj):
        return obj.bet_amount

    @admin.display(description="Время игры (сек)")
    def game_time_display(self, obj):
        return obj.game_time

    @admin.display(description="Интервал автостарта (сек)")
    def auto_start_interval_display(self, obj):
        return obj.auto_start_interval

    @admin.action(description="Запустить новую игровую сессию")
    def start_game_session(self, request, queryset):
        for game in queryset:
            if game.status != "active":
                self.message_user(request, f"Игра {game.name} не активна.", level="warning")
                continue

            try:
                GameSession.objects.create(
                    game=game,
                    start_time=now(),
                    end_time=now() + timedelta(seconds=game.game_time),
                    status="active",
                    commission_percent=game.commission_percent,
                )
                self.message_user(request, f"Игровая сессия для {game.name} успешно запущена.")
            except Exception as e:
                self.message_user(request, f"Ошибка при запуске сессии для {game.name}: {e}", level="error")

    @admin.action(description="Удалить выбранные валюты из игры")
    def remove_coins(self, request, queryset):
        for game in queryset:
            # Получаем валюты, которые были выбраны для удаления
            selected_coins = game.supported_coins.all()

            if selected_coins.exists():
                # Если валюты привязаны, предлагаем удалить их
                game.supported_coins.remove(*selected_coins)  # Удаляем валюты
                self.message_user(request, f"Валюты удалены из игры {game.name}")
            else:
                self.message_user(request, f"Валюты для игры {game.name} не найдены.", level="warning")

    def show_online_players_link(self, obj):
        url = reverse_lazy('admin-online-players') + f'?game_id={obj.id}'
        return format_html('<a class="button" href="{}">👥 Онлайн</a>', url)
    show_online_players_link.short_description = "Ссылка на онлайн-игроков"

    def show_online_players_list(self, obj):
        active_sessions = (
            UserGameSession.objects
            .filter(game_session__game=obj, status='active')
            .select_related('user')
            .order_by('-created_at')[:10]
        )

        players = [
            session.user.username
            for session in active_sessions
            if session.user and session.user.username
        ]

        if players:
            player_list = "".join([f"<li>{player}</li>" for player in players])
            return format_html("<ul style='margin: 0; padding-left: 20px;'>{}</ul>", player_list)
        else:
            return format_html("<span style='color:gray;'>Нет игроков</span>")
    show_online_players_list.short_description = "Онлайн игроки"

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.filter(status='active')
@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    list_display = ("game", "start_time", "end_time", "status")
    list_filter = ("status",)


class WithdrawalRequestAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'coin', 'amount', 'status', 'frozen_amount',
        'request_time', 'approved_time', 'approved_by',
        'rejection_reason', 'is_suspicious'
    )
    list_filter = ('status', 'coin', 'user')
    search_fields = ('user__username', 'coin__symbol', 'wallet_address')
    actions = ['approve_requests', 'reject_requests', 'finalize_withdrawal']

    def approve_requests(self, request, queryset):
        for withdrawal in queryset:
            if withdrawal.status == 'pending':
                withdrawal.approve(admin_user=request.user)
                self.message_user(request, f"Запрос {withdrawal.user.username} одобрен")
            else:
                self.message_user(request, f"Запрос {withdrawal.user.username} уже обработан")

    def reject_requests(self, request, queryset):
        for withdrawal in queryset:
            if withdrawal.status == 'pending':
                withdrawal.reject(admin_user=request.user, reason="Отклонено вручную")
                self.message_user(request, f"Запрос {withdrawal.user.username} отклонён")
            else:
                self.message_user(request, f"Запрос {withdrawal.user.username} уже обработан")

    def finalize_withdrawal(self, request, queryset):
        for withdrawal in queryset:
            if withdrawal.status == 'approved':
                withdrawal.finalize_withdrawal()
                self.message_user(request, f"Запрос {withdrawal.user.username} завершён")
            else:
                self.message_user(request, f"Запрос {withdrawal.user.username} ещё не одобрен")


admin.site.register(WithdrawalRequest, WithdrawalRequestAdmin)
admin.site.register(Coin, CoinAdmin)
admin.site.register(UserBalance, UserBalanceAdmin)
admin.site.register(GameSessionWinningCell, GameSessionWinningCellAdmin)
admin.site.register(UserGameSession, UserGameSessionAdmin)
admin.site.register(TransactionHistory, TransactionHistoryAdmin)
admin.site.register(CoinBetLimit, CoinBetLimitAdmin)
