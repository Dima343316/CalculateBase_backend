import logging
from datetime import timedelta
from decimal import Decimal
import aiohttp
import requests
from django.contrib.admin.views.decorators import staff_member_required
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.db.models import Sum
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.timezone import now
from django.db import transaction
import uuid
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import (
    IsAuthenticated,
    IsAdminUser,
    AllowAny
)
from rest_framework import status, viewsets
from tutorial.quickstart.serializers import UserSerializer
from rest_framework.exceptions import NotFound
from GamesCripth.settings import TELEGRAM_BOT_TOKEN
from games.tasks import finish_expired_game_sessions
from users.models import User

from .models import (
    UserBalance,
    Game,
    GameSession,
    UserGameSession,
    TransactionHistory,
    Coin, CoinBetLimit, WithdrawalRequest,
)
from .serializer import (TransactionRequestSerializer,
                         WithdrawalRequestSerializer,
                         JoinGameSessionSerializer,
                         DepositFundsSerializer, CoinBetLimitSerializer, CoinContractAddressSerializer
                         )
from .services.service_withdrawal import TransactionServiceWithdrawal
from .services.transaction_service import TransactionService, WALLET_ADDRESS
from .utils import send_telegram_messages_views, send_telegram_message_admin
from dotenv import load_dotenv
import environ
from rest_framework import generics, permissions
from .models import TransactionHistory
from .serializer import TransactionHistorySerializer


logger = logging.getLogger("transactions")


env = environ.Env()
environ.Env.read_env()
load_dotenv()


class JoinGameSessionView(APIView):
    """
    Позволяет пользователю присоединиться к активной игровой сессии,
    делая ставки на несколько ячеек с использованием их номеров.
    Пользователь может выбрать валюту для ставки.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, game_uid):
        user = request.user
        serializer = JoinGameSessionSerializer(data=request.data)
        if serializer.is_valid():
            cell_numbers = request.data.get("cell_numbers")
            bet_amount = request.data.get("bet_amount")
            session_id = request.data.get("session_id")
            coin_symbol = request.data.get("coin_symbol")  # Получаем валюту, которую выбрал пользователь

        if not coin_symbol:
            return Response({"error": "No coin symbol provided."}, status=status.HTTP_400_BAD_REQUEST)

        # Получаем игру
        game = get_object_or_404(Game, id=game_uid)

        # Проверяем, поддерживает ли игра выбранную валюту
        try:
            game_currency = game.supported_coins.get(symbol__iexact=coin_symbol)  # Получаем валюту
        except Coin.DoesNotExist:
            return Response({"error": f"Coin {coin_symbol} is not supported for this game."}, status=status.HTTP_400_BAD_REQUEST)

        # Валидируем данные ставок
        if not isinstance(cell_numbers, list) or not cell_numbers:
            return Response({"error": "Cell numbers must be a non-empty list."}, status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(bet_amount, (int, float, Decimal)) or Decimal(bet_amount) <= 0:
            return Response({"error": "Bet amount must be a positive number."}, status=status.HTTP_400_BAD_REQUEST)

        # Проверяем, активна ли игра
        if game.status != "active":
            return Response({"error": "The game is not active."}, status=status.HTTP_400_BAD_REQUEST)

        # Проверяем лимиты ставки для выбранной валюты
        coin_bet_limit = CoinBetLimit.objects.filter(coin=game_currency).first()
        if coin_bet_limit and Decimal(bet_amount) not in coin_bet_limit.allowed_bets:
            return Response({
                "error": f"Bet amount must be one of the following: {coin_bet_limit.allowed_bets}."
            }, status=status.HTTP_400_BAD_REQUEST)

        # Начинаем работу с транзакцией
        with transaction.atomic():
            # Получаем баланс пользователя по выбранной валюте
            user_balance = UserBalance.objects.select_for_update().filter(user=user, coin=game_currency).first()
            if not user_balance:
                return Response({"error": f"You do not have a balance in {game_currency.symbol}."},
                                status=status.HTTP_400_BAD_REQUEST)

            total_bet = Decimal(bet_amount) * len(cell_numbers)

            # Проверяем, хватает ли средств для ставки
            if user_balance.amount < total_bet:
                return Response({"error": "Insufficient funds to place the bet."},
                                status=status.HTTP_400_BAD_REQUEST)

            # Обрабатываем активную сессию
            if session_id:
                active_session = GameSession.objects.select_for_update().filter(
                    id=session_id, game=game, status="active"
                ).first()
                if not active_session:
                    return Response({"error": "Session not found or inactive."}, status=status.HTTP_400_BAD_REQUEST)
            else:
                # Если сессия не указана, создаем новую сессию
                active_session = GameSession.objects.select_for_update().filter(game=game, status="active").first()
                if not active_session or active_session.end_time <= now():
                    if len(cell_numbers) > game.cell_count:
                        return Response({"error": f"Cannot select more than {game.cell_count} cells for this game."},
                                        status=status.HTTP_400_BAD_REQUEST)
                    active_session = GameSession.objects.create(
                        game=game,
                        start_time=now(),
                        end_time=now() + timedelta(seconds=game.game_time),
                        status="active",
                        commission_percent=game.commission_percent,
                    )

            # Проверяем, были ли уже сделаны ставки на выбранные ячейки
            existing_bets = UserGameSession.objects.filter(
                user=user, game_session=active_session, cell_number__in=cell_numbers
            ).values_list("cell_number", flat=True)

            duplicate_cells = set(existing_bets)
            if duplicate_cells:
                return Response({"error": f"You have already placed bets on cells {list(duplicate_cells)}."},
                                status=status.HTTP_400_BAD_REQUEST)

            # Создаем новые ставки
            user_game_sessions = [
                UserGameSession(
                    user=user,
                    game_session=active_session,
                    bet_amount=bet_amount,
                    cell_number=cell_number,
                    coin=game_currency,
                    status="active"
                )
                for cell_number in cell_numbers
            ]
            UserGameSession.objects.bulk_create(user_game_sessions)

            # Обновляем баланс пользователя
            user_balance.amount -= total_bet
            user_balance.locked_amount += total_bet
            user_balance.save()

            # Записываем историю транзакции
            TransactionHistory.objects.create(
                user_balance=user_balance,
                amount=-total_bet,
                type="withdrawal",
                subtype="bet",
                related_game_session=active_session,
            )

            logger.info(
                "User %s placed a bet of %s %s on cells %s in session %s (game %s).",
                user.id, bet_amount, game_currency.symbol, cell_numbers, active_session.id, game.id
            )

        return Response({"message": "Successfully placed your bet.", "session_id": active_session.id},
                        status=status.HTTP_200_OK)

class DepositFundsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        user = request.user
        if not user.is_authenticated:
            return Response({"error": "You need to authenticate via Telegram."}, status=status.HTTP_403_FORBIDDEN)

        if not user.memo_phrase:
            return Response({"error": "User does not have a memo phrase. Transaction blocked."},
                            status=status.HTTP_400_BAD_REQUEST)

        serializer = DepositFundsSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        coin_symbol = serializer.validated_data['coin']
        decimals_map = {"USD₮": 6, "DOGS": 9, "TON": 9}

        try:
            transactions = TransactionService.fetch_transactions()
            found_transaction = None
            amount = None

            # 🔁 Ищем первую подходящую и НЕОБРАБОТАННУЮ транзакцию
            for action in transactions:
                details = action.get("details", {})
                tx_amount = details.get("value") or details.get("amount")
                receiver = details.get("receiver")
                comment = details.get("comment")
                trace_id = action.get("trace_id")

                if receiver and receiver != WALLET_ADDRESS:
                    continue

                tx_coin_symbol = "TON" if action.get("type") != "jetton_transfer" else TransactionService.get_jetton_symbol(details.get("asset"))
                tx_decimals = decimals_map.get(tx_coin_symbol, 9)

                if tx_amount is None or comment is None or trace_id is None:
                    continue

                try:
                    amount = Decimal(int(tx_amount)) / Decimal(10 ** tx_decimals)
                except Exception:
                    continue

                if tx_coin_symbol == coin_symbol and comment == user.memo_phrase:
                    if not TransactionHistory.objects.filter(trace_id=trace_id).exists():
                        found_transaction = action
                        break

            if not found_transaction:
                return Response({"error": "Transaction not found or already processed."},
                                status=status.HTTP_404_NOT_FOUND)

            trace_id = found_transaction.get("trace_id")

            # Получаем коин
            coin = get_object_or_404(Coin, symbol=coin_symbol)
            user_balance, _ = UserBalance.objects.get_or_create(user=user, coin=coin, defaults={"amount": Decimal(0)})

            # Обновляем баланс
            user_balance.amount += amount
            user_balance.save(update_fields=["amount"])

            # Записываем в историю
            TransactionHistory.objects.create(
                user_balance=user_balance,
                amount=amount,
                type="arrival",
                subtype="deposit",
                trace_id=trace_id,
                transaction_id=str(uuid.uuid4())
            )

            # Уведомление в Telegram
            message = f"✅ Ваш баланс в игре PING пополнен на {amount} {coin.symbol}!"
            send_telegram_messages_views(user.telegram_id, message)

            return Response({"status": "success", "message": f"Deposited {amount} {coin.symbol} successfully."})

        except Exception as e:
            return Response({"error": "Internal server error while processing transaction."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class FinishGameSessionView(APIView):
    """
    Завершение игровой сессии.
    """

    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request, session_id):
        game_session = get_object_or_404(GameSession, id=session_id)

        if game_session.status != "active":
            return Response(
                {"error": "Game session is not active."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        finish_expired_game_sessions.delay(session_id)

        return Response(
            {"message": "Game session finish is being processed."},
            status=status.HTTP_202_ACCEPTED,
        )


class CheckUserBalanceView(APIView):
    """
    Получить балансы пользователя по монетам.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        balances = UserBalance.objects.filter(user=user)

        balance_data = [
            {
                "coin": user_balance.coin.symbol,  # Символ монеты (например, BTC)
                "amount": str(user_balance.amount),  # Свободный баланс
                "locked_amount": str(user_balance.locked_amount),  # Замороженные средства
            }
            for user_balance in balances
        ]

        return JsonResponse({"balances": balance_data}, status=200)


class GameDrawingStatsView(APIView):

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    """
    Вьюха для отображения статистики по розыгрышу.
    """

    def get(self, request, session_id):
        try:
            game_session = GameSession.objects.get(id=session_id)
        except GameSession.DoesNotExist:
            return Response({"detail": "Game session not found."}, status=status.HTTP_404_NOT_FOUND)

        # Получаем данные о ставках и выигрышах/проигрышах
        user_sessions = UserGameSession.objects.filter(game_session=game_session)

        total_bet_amount = user_sessions.aggregate(total_bet=Sum('bet_amount'))['total_bet'] or 0.0
        total_winnings = user_sessions.filter(result='win').aggregate(total_win=Sum('winning_amount'))[
                             'total_win'] or 0.0
        total_losses = user_sessions.filter(result='lose').aggregate(total_loss=Sum('bet_amount'))['total_loss'] or 0.0

        # Подготовим данные для отображения
        context = {
            'session_id': game_session.id,
            'game_name': game_session.game.name,
            'bet_amount': total_bet_amount,
            'winnings': total_winnings,
            'losses': total_losses,
        }

        return Response(context, status=status.HTTP_200_OK)


class CoinBetLimitListView(APIView):
    """
    Получение списка лимитов ставок по каждой валюте.
    Безопасно, только для чтения.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        bet_limits = CoinBetLimit.objects.select_related('coin').all()
        serializer = CoinBetLimitSerializer(bet_limits, many=True)
        return Response(serializer.data)

class UserTransactionStatsView(APIView):


    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    """
    Вьюха для отображения статистики транзакций пользователя (ставки, выигрыши, проигрыши).
    """

    def get(self, request):
        user = request.user

        bet_transactions = TransactionHistory.objects.filter(
            user_balance__user=user,
            subtype='bet'
        ).aggregate(
            total_bet_count=Sum('amount'),
            total_bet_amount=Sum('amount')
        )

        win_transactions = TransactionHistory.objects.filter(
            user_balance__user=user,
            subtype='win'
        ).aggregate(
            total_win_count=Sum('amount'),
            total_win_amount=Sum('amount')
        )

        loss_transactions = TransactionHistory.objects.filter(
            user_balance__user=user,
            subtype='bet'
        ).exclude(subtype='win').aggregate(
            total_loss_count=Sum('amount'),
            total_loss_amount=Sum('amount')
        )

        context = {
            'total_bet_count': bet_transactions['total_bet_count'],
            'total_bet_amount': bet_transactions['total_bet_amount'] or 0.0,
            'total_win_count': win_transactions['total_win_count'],
            'total_win_amount': win_transactions['total_win_amount'] or 0.0,
            'total_loss_count': loss_transactions['total_loss_count'],
            'total_loss_amount': loss_transactions['total_loss_amount'] or 0.0,
        }

        return Response(context, status=status.HTTP_200_OK)


class TonTransactionsView(APIView):
    authentication_classes = []  # Отключаем любую аутентификацию
    permission_classes = [AllowAny]  # Разрешаем всем доступ

    @staticmethod
    async def fetch_jetton_info(asset_address: str):
        """
        Асинхронно запрашивает информацию о jetton с использованием aiohttp.
        """
        try:
            async with aiohttp.ClientSession() as session:
                TONAPI_URL = env("TONAPI_URL")
                async with session.get(f"{TONAPI_URL}{asset_address}") as response:
                    if response.status != 200:
                        logger.error(f"Ошибка получения jetton информации для {asset_address}")
                        return None
                    return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"Ошибка запроса к TONAPI для jetton: {e}")
            return None

    def get(self, request):
        account = "0:2EDEF3D66BC94CE1E5A0CE8657EFC7682C3DDCEAAE605CD593CC9F254DD00435"
        params = {"account": account, "limit": 50, "sort": "desc"}

        response = requests.get(env("TONCENTER_API_URL"), params=params)
        if response.status_code != 200:
            return Response({"error": "Не удалось получить транзакции"}, status=500)

        data = response.json()
        transactions = []

        for action in data.get("actions", []):
            tx_type = action.get("type")
            if tx_type in ["ton_transfer", "jetton_transfer"]:
                transaction = self.process_transaction(action, tx_type)
                if transaction:
                    transactions.append(transaction)

        return Response(transactions)

    def process_transaction(self, action, tx_type):
        """
        Обрабатывает каждую транзакцию в зависимости от ее типа.
        """
        try:
            if tx_type == "ton_transfer":
                currency = "TON"
                amount = int(action["details"].get("value", 0)) / 1e9
                transaction_type = "Вывод TON"
            elif tx_type == "jetton_transfer":
                asset_address = action["details"].get("asset")
                jetton_info = aiohttp.run(self.fetch_jetton_info(asset_address))
                if jetton_info is None:
                    return None  # Если не удается получить информацию о jetton, пропускаем
                currency = jetton_info.get("metadata", {}).get("symbol", "Unknown")
                amount = int(action["details"].get("amount", 0)) / 1e9
                transaction_type = f"Вывод {currency}"  # Оформляем вывод средств для jetton
            else:
                return None  # Пропускаем другие типы транзакций

            return {
                "tx_id": action.get("trace_id"),
                "from": action["details"].get("source", action["details"].get("sender")),
                "to": action["details"].get("destination", action["details"].get("receiver")),
                "amount": amount,
                "currency": currency,
                "timestamp": action.get("end_utime"),
                "type": transaction_type,  # Добавляем тип транзакции
            }
        except Exception as e:
            logger.error(f"Ошибка при обработке транзакции: {e}")
            return None


class TransactionView(APIView):
    """
    Проверка транзакции, верификация пользователя и уведомления в Telegram.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TransactionRequestSerializer(data=request.data)
        if not serializer.is_valid():
            logger.warning(f"Invalid transaction data: {serializer.errors}")
            raise ValidationError(serializer.errors, code=status.HTTP_400_BAD_REQUEST)

        transaction_type = serializer.validated_data['type']
        amount = serializer.validated_data['amount']
        currency = serializer.validated_data['currency']
        wallet_address = serializer.validated_data['wallet_address']

        telegram_user_id = request.session.get('telegram_user_id')
        if not telegram_user_id:
            logger.warning(f"Unauthorized attempt - No Telegram ID. IP: {request.META.get('REMOTE_ADDR')}")
            raise ValidationError({"error": "Telegram user is not authenticated."},
                                  code=status.HTTP_401_UNAUTHORIZED)


        try:
            user = User.objects.get(telegram_id=telegram_user_id)
        except User.DoesNotExist:
            logger.warning(f"User not found: Telegram ID = {telegram_user_id}")
            raise ValidationError({"error": "User not found."}, code=status.HTTP_404_NOT_FOUND)

        is_valid, message = TransactionServiceWithdrawal.validate_transaction(user,
                                                                              amount,
                                                                              currency
                                                                              )
        if not is_valid:
            if "Suspicious" in message:
                TransactionServiceWithdrawal.notify_suspicious_transaction(user,
                                                                           amount,
                                                                           currency,
                                                                           wallet_address
                                                                           )
            logger.warning(f"Transaction validation failed for user {user.telegram_id}: {message}")
            self.send_telegram_message(user.telegram_id, f"⚠️ Ошибка: {message}")
            raise ValidationError({"error": message}, code=status.HTTP_400_BAD_REQUEST)

        logger.info(f"Transaction validated for user {user.telegram_id}. Amount: {amount} {currency}")
        self.send_telegram_message(user.telegram_id, f"✅ Ваш вывод {amount} {currency} успешно подтвержден! 🚀")

        return Response({"status": message}, status=status.HTTP_200_OK)

    @staticmethod
    def send_telegram_message(chat_id, message):
        """
        Отправка сообщения пользователю в Telegram через API бота.
        """
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message
        }
        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Ошибка отправки сообщения в Telegram: {e}")


class WithdrawalView(APIView):
    """Обработчик вывода средств"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        data = request.data

        serializer = WithdrawalRequestSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        amount = serializer.validated_data['amount']
        currency = serializer.validated_data['currency']
        wallet_address = serializer.validated_data['wallet_address']

        try:
            user_balance = UserBalance.objects.get(user=user, coin__symbol=currency)
        except UserBalance.DoesNotExist:
            return Response({'error': 'Currency balance not found'}, status=status.HTTP_404_NOT_FOUND)

        total_winnings = TransactionHistory.objects.filter(
            user_balance=user_balance,
            type="arrival",
            subtype__in=["win", "refund"]
        ).aggregate(total=Sum('amount'))['total'] or Decimal('0')

        suspicious = amount > max(total_winnings * 10, 1000)

        withdrawal_request = WithdrawalRequest.objects.create(
            user=user,
            coin=Coin.objects.get(symbol=currency),  # Здесь предполагаем, что вы получаете объект Coin по символу
            amount=amount,
            wallet_address=wallet_address,
            frozen_amount=amount  # Замораживаем средства
        )

        admin_message = f"🔔 Новый запрос на вывод: {user.username} ({user.first_name} {user.last_name})\n" \
                        f"Telegram ID {user.telegram_id}\n" \
                        f"💰 Сумма: {amount} {currency}\n" \
                        f"🏦 Кошелек: {wallet_address}\n" \
                        f"⚠️ Подозрительность: {'Да' if suspicious else 'Нет'}"

        send_telegram_message_admin(env("ADMIN_TELEGRAM_USERNAME"), admin_message)

        return Response({'message': 'Withdrawal request submitted'},
                        status=status.HTTP_200_OK)


class MyWinsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        transactions = TransactionHistory.objects.filter(
            user_balance__user=request.user,
            type='arrival',
            subtype='win'
        ).select_related(
            'related_user_game_session__game_session__game',
            'user_balance__coin'
        ).order_by('-created_at')

        data = []
        for tx in transactions:
            game_session = tx.related_user_game_session.game_session if tx.related_user_game_session else None
            game = game_session.game if game_session else None
            if game:
                data.append({
                    "game_name": game.name,
                    "cell_count": game.cell_count,
                    "bet": float(tx.related_user_game_session.bet_amount),
                    "win": float(tx.amount),
                    "coin": game.coin.symbol,
                    "created_at": tx.created_at
                })

        return Response({"wins": data}, status=status.HTTP_200_OK)

class MyLossesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        losses = UserGameSession.objects.filter(
            user=request.user,
            result='lose',
            status='finished'
        ).select_related('game_session__game', 'game_session__game__coin').order_by('-created_at')

        data = [{
            "game_name": l.game_session.game.name,
            "cell_count": l.game_session.game.cell_count,
            "bet": float(l.bet_amount),
            "coin": l.game_session.game.coin.symbol,
            "created_at": l.created_at
        } for l in losses]

        return Response({"losses": data}, status=status.HTTP_200_OK)

def admin_online_players(request, game_id):
    game = get_object_or_404(Game, pk=game_id)

    # Ищем активную игровую сессию
    active_session = GameSession.objects.filter(game=game, status='active').first()

    if not active_session:
        return render(request, 'game/players.html', {
            'game': game,
            'message': 'Нет активных сессий.'
        })

    # Получаем всех пользователей, которые находятся в активной сессии
    players = UserGameSession.objects.filter(game_session=active_session, status='active')

    return render(request, 'game/players.html', {
        'game': game,
        'players': players,
        'count': players.count(),
    })



class LastDepositsView(generics.ListAPIView):
    serializer_class = TransactionHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        coin_symbol = self.request.query_params.get("coin")
        qs = TransactionHistory.objects.filter(
            user_balance__user=self.request.user,
            type='arrival',
            subtype='deposit'
        ).select_related('user_balance', 'user_balance__coin')

        if coin_symbol:
            qs = qs.filter(user_balance__coin__symbol__iexact=coin_symbol.strip())

        return qs.order_by('-created_at')[:5]




class LastWithdrawalsView(generics.ListAPIView):
    serializer_class = TransactionHistorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        coin_symbol = self.request.query_params.get("coin")
        queryset = TransactionHistory.objects.filter(
            user_balance__user=self.request.user,
            type='withdrawal'
        )

        if coin_symbol:
            queryset = queryset.filter(user_balance__coin__symbol__iexact=coin_symbol)

        return queryset.order_by('-created_at')[:5]

class AvailableGamesByCoinView(APIView):
    """
    Возвращает доступные активные игровые сессии и лимиты ставок по выбранной валюте.
    """
    permission_classes = [AllowAny]

    def get(self, request, symbol):
        try:
            coin = Coin.objects.get(symbol__iexact=symbol)
        except Coin.DoesNotExist:
            raise NotFound("Валюта не найдена.")

        try:
            limit = CoinBetLimit.objects.get(coin=coin)
        except CoinBetLimit.DoesNotExist:
            raise NotFound("Лимиты ставок не заданы для этой валюты.")

        active_sessions = GameSession.objects.filter(
            game__coin=coin,
            game__bet_amount__in=limit.allowed_bets,
            game__status='active',
            status='active',
            end_time__gt=now()
        ).select_related("game")

        # Группируем по играм
        games_data = {}
        for session in active_sessions:
            game = session.game
            game_id = str(game.id)

            if game_id not in games_data:
                games_data[game_id] = {
                    "game_id": game_id,
                    "game_name": game.name,
                    "cell_count": game.cell_count,
                    "bet_amount": str(game.bet_amount),
                    "coin_symbol": coin.symbol,
                    "sessions": []
                }

            games_data[game_id]["sessions"].append({
                "session_id": str(session.id),
                "end_time": session.end_time.isoformat(),
                "remaining_time": max(0, int((session.end_time - now()).total_seconds()))
            })

        return Response({
            "coin": coin.symbol,
            "allowed_bets": [str(bet) for bet in limit.allowed_bets],
            "games": list(games_data.values())
        })


def show_qr_code(request, symbol):
    coin = get_object_or_404(Coin, symbol=symbol)

    if coin.qr_code_image:
        return HttpResponse(coin.qr_code_image.open().read(), content_type='image/png')

    return HttpResponse("QR-код не найден", status=404)

class CoinContractAddressView(APIView):
    permission_classes =  [AllowAny]
    """
    Возвращает contract_address для указанной монеты по symbol.
    """

    def get(self, request, symbol):
        coin = get_object_or_404(Coin, symbol__iexact=symbol)
        serializer = CoinContractAddressSerializer(coin)
        return Response(serializer.data, status=status.HTTP_200_OK)


__all__=()
