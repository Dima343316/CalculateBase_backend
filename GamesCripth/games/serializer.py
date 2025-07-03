import string
from decimal import Decimal
from rest_framework import serializers

from games.models import CoinBetLimit, TransactionHistory, Coin


class CoinContractAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coin
        fields = ['contract_address']


class TransactionRequestSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=["jetton_transfer", "ton_transfer"])  # Тип транзакции
    amount = serializers.DecimalField(max_digits=20, decimal_places=8)  # Сумма для вывода
    currency = serializers.ChoiceField(choices=["TON", "USDT", "DOGS"])  # Валюта
    wallet_address = serializers.CharField(max_length=255)  # Адрес кошелька для вывода

class WithdrawalRequestSerializer(serializers.Serializer):
    type = serializers.CharField()
    amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    currency = serializers.CharField(max_length=10)
    wallet_address = serializers.CharField(max_length=255)

    def validate_type(self, value):
        if value != "ton_transfer":
            raise serializers.ValidationError("Invalid transaction type")
        return value

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Invalid withdrawal amount")
        return value

    def validate_currency(self, value):
        # Можно добавить проверку на допустимые валюты
        allowed_currencies = ['DOGS', 'TON', 'BTC']  # Пример валют
        if value not in allowed_currencies:
            raise serializers.ValidationError("Invalid currency")
        return value

    def validate_wallet_address(self, value):
        if len(value) != 48:
            raise serializers.ValidationError("Invalid wallet address length")

        allowed_chars = string.ascii_letters + string.digits  # Все буквы и цифры


        if not all(c in allowed_chars for c in value):
            raise serializers.ValidationError("Invalid characters in wallet address")

        return value

class JoinGameSessionSerializer(serializers.Serializer):
    """
    Сериализатор для вьюхи присоединения к активной игровой сессии и создания ставок.
    """
    cell_numbers = serializers.ListField(
        child=serializers.IntegerField(),
        required=True,
        allow_empty=False,
        help_text="Список номеров ячеек, на которые пользователь ставит."
    )
    bet_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2,
        required=True,
        help_text="Сумма ставки."
    )
    session_id = serializers.IntegerField(
        required=False, allow_null=True,
        help_text="ID активной игровой сессии (необязательное поле)."
    )

class DepositFundsSerializer(serializers.Serializer):
    """
    Сериализатор для депозита средств в игровой баланс.
    Пользователь указывает только валюту (coin), сумма берётся из транзакции.
    """
    ALLOWED_COINS = {"TON", "DOGS", "USD₮"}  # Разрешённые валюты

    coin = serializers.ChoiceField(
        choices=ALLOWED_COINS,
        required=True,
        help_text="Символ валюты (TON, DOGS, USD₮)."
    )

class CoinBetLimitSerializer(serializers.ModelSerializer):
    coin = serializers.CharField(source='coin.name')  # можно заменить на 'symbol' или другое поле

    class Meta:
        model = CoinBetLimit
        fields = [
            'coin',
            'allowed_bets'
        ]


class TransactionHistorySerializer(serializers.ModelSerializer):
    coin = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()

    class Meta:
        model = TransactionHistory
        fields = [
            'amount',
            'type',
            'subtype',
            'created_at',
            'memo_phrase',
            'transaction_id',
            'trace_id',
            'coin',
        ]

    def get_coin(self, obj):
        if obj.user_balance and obj.user_balance.coin:
            return obj.user_balance.coin.symbol
        return None

    def get_amount(self, obj):
        amt = obj.amount
        if not isinstance(amt, Decimal):
            try:
                amt = Decimal(str(amt))
            except:
                return str(amt)  # fallback, если не конвертируется

        normalized = amt.normalize()
        # Преобразуем в строку без экспоненты и лишних нулей
        amt_str = format(normalized, 'f')
        if '.' in amt_str:
            amt_str = amt_str.rstrip('0').rstrip('.')
        return amt_str

__all__=()
