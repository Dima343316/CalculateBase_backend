import logging
import uuid
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.contrib.postgres.fields import ArrayField
from django.db import models, transaction
from datetime import timedelta
from django.utils.timezone import now
from users.models import User


logger = logging.getLogger(__name__)


class Coin(models.Model):
    name = models.CharField(max_length=50)
    symbol = models.CharField(max_length=10, unique=True)
    coin_type = models.CharField(max_length=50, null=True, blank=True)
    contract_address = models.CharField(max_length=255, null=True, blank=True)

    qr_code_url = models.URLField(null=True, blank=True, help_text="Ссылка на изображение QR-кода")
    qr_code_image = models.ImageField(upload_to='qr_codes/', null=True, blank=True, help_text="Локальный файл QR-кода")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Монета"
        verbose_name_plural = "Монеты"

    def __str__(self):
        return self.symbol


# -------------------------
# Лимиты валют
# -------------------------

class CoinBetLimit(models.Model):
    coin = models.OneToOneField(Coin, on_delete=models.CASCADE)
    allowed_bets = ArrayField(
        models.DecimalField(max_digits=20, decimal_places=8),
        blank=False,
        default=list
    )

    def clean(self):
        if not all(isinstance(amount, (int, float, Decimal)) and amount > 0 for amount in self.allowed_bets):
            raise ValidationError("Each bet amount must be a positive number.")


        if len(self.allowed_bets) != len(set(self.allowed_bets)):
            raise ValidationError("Bet amounts cannot contain duplicates.")

    class Meta:
        verbose_name = "Установить лимит на монеты"
        verbose_name_plural = "Установить лимит на монеты"

    def __str__(self):
        return f"Лимит ставки для {self.coin.name}: {self.allowed_bets}"

# -------------------------
# Балансы пользователей
# -------------------------
class UserBalance(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="balances")
    coin = models.ForeignKey(Coin, on_delete=models.CASCADE)
    amount = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        default=0.0
    )
    locked_amount = models.DecimalField(
        max_digits=18,
        decimal_places=8,
        default=0.0
    )
    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Баланс пользователя"
        verbose_name_plural = "Баланс пользователя"

    def __str__(self):
        return f"{self.user.username} - {self.coin.symbol}"

# -------------------------
class Game(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    name = models.CharField(max_length=255)  # Например, "game_3_users_btc"
    cell_count = models.PositiveIntegerField()  # Количество ячеек в игре
    supported_coins = models.ManyToManyField(Coin, related_name="games")  # Множественные валюты для игры
    bet_amount = models.DecimalField(max_digits=18, decimal_places=8)
    commission_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=15.00
    )
    game_time = models.PositiveIntegerField()
    is_processing = models.BooleanField(default=False)
    status = models.CharField(max_length=20, default='active', choices=[
        ('active', 'Active'),
        ('disabled', 'Disabled'),
        ('archived', 'Archived')
    ])
    auto_start_interval = models.PositiveIntegerField(default=60)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    @classmethod
    def create_game(cls,
                    name,
                    supported_coins,  # Теперь можно передавать список валют
                    bet_amount,
                    commission_percent,
                    game_time,
                    cell_count
                    ):
        game = cls(
            name=name,
            bet_amount=bet_amount,
            commission_percent=commission_percent,
            game_time=game_time,
            cell_count=cell_count,
        )
        game.save()

        # Добавляем валюты в игру
        game.supported_coins.set(supported_coins)  # Это установит все переданные валюты для игры
        return game

    class Meta:
        verbose_name = "Игры"
        verbose_name_plural = "Игры"

# -------------------------
# Сессии игры
# -------------------------
class GameSession(models.Model):
    game = models.ForeignKey('Game', on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('finished', 'Finished'),
        ('canceled', 'Canceled')
    ])
    commission_percent = models.DecimalField(max_digits=5,
                                             decimal_places=2
                                             )
    total_bet_amount = models.DecimalField(max_digits=18,
                                           decimal_places=8,
                                           default=0.0
                                           )

    commission_amount = models.DecimalField(max_digits=18,
                                            decimal_places=8,
                                            default=0.0
                                            )
    is_processing = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """Переопределенный метод сохранения сессии.
           Если end_time не задан, вычисляем его на основе game.game_time.
        """
        if not self.end_time:
            self.end_time = self.start_time + timedelta(seconds=self.game.game_time)
        super().save(*args, **kwargs)


    def __str__(self):
        return f"Session of {self.game.name}"

    def is_active(self):
        """Проверка, активна ли игровая сессия"""
        return self.status == "active" and now() < self.end_time

    def is_finished(self):
        """Проверка, завершена ли игровая сессия"""
        return self.status == "finished" or now() >= self.end_time

    @classmethod
    def create_session(cls, game, start_time, status='active'):
        """
        Создает игровую сессию для данной игры с использованием транзакции и обновлением флага is_processing.
        При проверке учитываем только сессии со статусом 'pending' или 'active'.
        """
        session = None
        try:
            with transaction.atomic():
                existing_session = cls.objects.select_for_update().filter(
                    game=game,
                    is_processing=True,
                    status__in=["pending", "active"]
                ).first()
                if existing_session:
                    raise Exception(f"Сессия для игры {game.name} уже в процессе создания.")

                session = cls(
                    game=game,
                    start_time=start_time,
                    status=status,
                    commission_percent=game.commission_percent,
                    is_processing=True
                )
                session.save()
                cls.objects.filter(id=session.id).update(is_processing=False)
                session.refresh_from_db()
                logger.info(f"Создана сессия {session.id} для игры {game.name} с is_processing={session.is_processing}.")
        except Exception as e:
            if session:
                cls.objects.filter(id=session.id).update(is_processing=False)
            logger.error(f"Ошибка при создании сессии для игры {game.name}: {e}")
            raise e
        return session

    class Meta:
        verbose_name = "Игровые сессии"
        verbose_name_plural = "Игровые сессии"


# Выигрышные ячейки
# -------------------------
class GameSessionWinningCell(models.Model):
    game_session = models.ForeignKey(
        GameSession,
        on_delete=models.CASCADE,
        related_name="winning_cells"
    )
    cell_number = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Выигрышные ячейки"
        verbose_name_plural = "Выигрышные ячейки"

    def __str__(self):
        return f"Winning Cell {self.cell_number} for Session {self.game_session.id}"


# -------------------------
# Участие пользователей в игре
# -------------------------
class UserGameSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    coin = models.ForeignKey(Coin, on_delete=models.CASCADE, null=True, blank=True, related_name="user_game_sessions")

    game_session = models.ForeignKey(GameSession, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, default='pending', choices=[
        ('pending', 'Pending'),
        ('active', 'Active'),
        ('finished', 'Finished'),
        ('canceled', 'Canceled')
    ])
    cell_number = models.PositiveIntegerField(null=True, blank=True)  # Выбранная ячейка
    bet_amount = models.DecimalField(max_digits=18, decimal_places=8)  # Размер ставки
    result = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        choices=[('win', 'Win'),
                 ('lose', 'Lose')
                 ]
    )
    winning_amount = models.DecimalField(max_digits=18, decimal_places=8, default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        """При сохранении обновляем активность пользователя"""
        self.user.update_last_activity()
        logger.info(f"Updated activity for user {self.user.username} during game session {self.game_session.id}")
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Игровые сессии игроков"
        verbose_name_plural = "Игровые сессии игроков"

    def __str__(self):
        return f"{self.user.username} in {self.game_session.game.name}"


# -------------------------
# История транзакций
# -------------------------
class TransactionHistory(models.Model):
    user_balance = models.ForeignKey(UserBalance, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=18, decimal_places=8)
    type = models.CharField(max_length=20, choices=[
        ('arrival', 'Arrival'),
        ('withdrawal', 'Withdrawal'),
        ('transfer', 'Transfer'),
        ('referral', 'Реферальный доход'),
    ])
    subtype = models.CharField(max_length=20,
                               null=True, blank=True, choices=[
        ('bet', 'Bet'),
        ('win', 'Win'),
        ('commission', 'Commission'),
        ('deposit', 'Deposit'),
        ('refund', 'Refund')
    ])
    related_game_session = models.ForeignKey(
        GameSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    related_user_game_session = models.ForeignKey(
        UserGameSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    memo_phrase = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)

    transaction_id = models.UUIDField(unique=True, default=uuid.uuid4)
    trace_id = models.CharField(max_length=255, null=True, blank=True, unique=True)  # Новое поле для trace_id

    @property
    def user_name(self):
        user = self.user_balance.user
        if user.username:
            return user.username
        elif user.telegram_id:
            return str(user.telegram_id)
        return 'Unknown'

    def __str__(self):
        return f"Transaction for {self.user_name} ({self.type})"

    class Meta:
        verbose_name = "Иcтория тразакций"
        verbose_name_plural = "Иcтория тразакций"

    def save(self, *args, **kwargs):
        if not self.transaction_id:  # Только если не указан transaction_id, генерируем новый
            self.transaction_id = str(uuid.uuid4())  # Генерация уникального ID
        super().save(*args, **kwargs)


class WithdrawalRequest(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    coin = models.ForeignKey(Coin, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=18, decimal_places=8)
    wallet_address = models.CharField(max_length=255)
    status = models.CharField(
        max_length=20,
        choices=[('pending', 'Pending'),
                 ('approved', 'Approved'),
                 ('rejected', 'Rejected')
                 ],
        default='pending'
    )
    frozen_amount = models.DecimalField(max_digits=18, decimal_places=8)  # Замороженная сумма (до подтверждения)
    request_time = models.DateTimeField(auto_now_add=True)  # Время создания запроса
    approved_time = models.DateTimeField(null=True, blank=True)  # Время одобрения (если одобрено)
    rejected_time = models.DateTimeField(null=True, blank=True)  # Время отклонения (если отклонено)
    approved_by = models.ForeignKey(User, null=True, blank=True, related_name='approving_user', on_delete=models.SET_NULL)  # Админ, который одобрил запрос
    rejection_reason = models.TextField(null=True, blank=True)  # Причина отклонения, если отклонено
    is_suspicious = models.BooleanField(default=False)  # Флаг подозрительности транзакции

    def __str__(self):
        return f"Withdrawal Request for {self.user.username} - {self.coin.symbol} {self.amount}"

    def approve(self, admin_user):
        """Метод для одобрения запроса и списания средств"""
        with transaction.atomic():
            user_balance = UserBalance.objects.get(user=self.user, coin=self.coin)

            if user_balance.amount < self.amount:
                raise ValidationError("Insufficient balance to approve withdrawal request.")

            user_balance.amount -= self.amount
            user_balance.locked_amount += self.amount
            user_balance.save()

            self.status = 'approved'
            self.approved_time = now()
            self.approved_by = admin_user
            self.save()

            TransactionHistory.objects.create(
                user_balance=user_balance,
                amount=self.amount,
                type='withdrawal',
                subtype='pending',
                memo_phrase=f"Withdrawal request {self.id} approved and funds locked"
            )

    def reject(self, admin_user, reason):
        """Метод для отклонения запроса"""
        with transaction.atomic():
            self.status = 'rejected'
            self.rejection_reason = reason
            self.rejected_time = now()
            self.save()

            TransactionHistory.objects.create(
                user_balance=self.user.balances.get(coin=self.coin),
                amount=self.amount,
                type='withdrawal',
                subtype='rejected',
                memo_phrase=f"Withdrawal request {self.id} rejected"
            )

    def finalize_withdrawal(self):
        """Метод для окончательного списания средств после одобрения"""
        with transaction.atomic():
            user_balance = UserBalance.objects.get(user=self.user, coin=self.coin)
            user_balance.amount -= self.amount
            user_balance.locked_amount -= self.amount
            user_balance.save()

            TransactionHistory.objects.create(
                user_balance=user_balance,
                amount=self.amount,
                type='withdrawal',
                subtype='completed',
                memo_phrase=f"Withdrawal {self.id} completed"
            )

            self.status = 'completed'
            self.save()

    class Meta:
        verbose_name = "Заявка на вывод"
        verbose_name_plural = "Заявка на вывод"

__all__=()