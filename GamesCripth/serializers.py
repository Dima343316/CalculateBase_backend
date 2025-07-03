from rest_framework import serializers
from games.models import GameSession, UserGameSession, TransactionHistory


class GameSessionSerializer(serializers.ModelSerializer):
    """
    Сериализатор для сессии игры.
    """
    class Meta:
        model = GameSession
        fields = [
            'id',
            'game',
            'start_time',
            'end_time',
            'status',
            'commission_percent',
            'total_bet_amount',
            'commission_amount'
        ]


class UserGameSessionSerializer(serializers.ModelSerializer):
    """
    Сериализатор для участия пользователя в игровой сессии.
    """
    class Meta:
        model = UserGameSession
        fields = [
            'user',
            'game_session',
            'status',
            'cell_number',
            'bet_amount',
            'result',
            'winning_amount'
        ]


class TransactionHistorySerializer(serializers.ModelSerializer):
    """
    Сериализатор для транзакций пользователя.
    """
    user_name = serializers.CharField(
        source="user_balance.user.username", read_only=True
    )

    class Meta:
        model = TransactionHistory
        fields = [
            'user_name',
            'amount',
            'type',
            'subtype',
            'created_at'
        ]
