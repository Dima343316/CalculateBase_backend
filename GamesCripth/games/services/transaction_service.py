import logging
import uuid
from decimal import Decimal
from django.db import transaction, IntegrityError
from users.models import User
from games.models import UserBalance, TransactionHistory, Coin
import requests
import environ

env = environ.Env()
environ.Env.read_env()


# Берём значения из .env
TON_API_URL = env("TON_API_URL")
TON_JETTON_INFO_URL = env("TON_JETTON_INFO_URL")
WALLET_ADDRESS = env("WALLET_ADDRESS")
SUPPORTED_COINS = env.list("SUPPORTED_COINS", default=["TON", "USD₮", "DOGS"])


logger = logging.getLogger("transactions")

class TransactionService:
    """Сервис обработки крипто-транзакций"""

    @staticmethod
    def fetch_transactions():
        """Получает последние транзакции с кошелька."""
        try:
            logger.info("🔄 Запрашиваем последние транзакции...")
            response = requests.get(f"{TON_API_URL}?account={WALLET_ADDRESS}&limit=20&sort=desc")
            response.raise_for_status()

            transactions = response.json().get("actions", [])
            if not transactions:
                logger.warning("⚠️ Ответ от API не содержит транзакций.")
            logger.info(f"✅ Получено {len(transactions)} транзакций.")
            return transactions
        except requests.RequestException as e:
            logger.error(f"❌ Ошибка при запросе транзакций: {e}", exc_info=True)
            return []

    @staticmethod
    def get_jetton_symbol(asset_address):
        """Определяет символ токена по его адресу."""
        try:
            response = requests.get(f"{TON_JETTON_INFO_URL}{asset_address}")
            response.raise_for_status()

            symbol = response.json().get("metadata", {}).get("symbol")
            if symbol:
                logger.info(f"✅ Символ токена: {symbol}")
            return symbol
        except requests.RequestException as e:
            logger.error(f"❌ Ошибка при получении символа токена: {e}", exc_info=True)
            return None

    @staticmethod
    @transaction.atomic
    def process_transaction(action):
        """Обрабатывает транзакцию."""
        if not action.get("success"):
            logger.warning("⚠️ Транзакция не удалась.")
            return

        trace_id = action.get("trace_id")
        details = action.get("details", {})
        comment = details.get("comment")
        amount = details.get("value")
        asset_address = details.get("asset")

        if not all([trace_id, comment, amount]):
            logger.warning(f"⚠️ Пропущена некорректная транзакция: {action}")
            return

        if TransactionHistory.objects.filter(trace_id=trace_id).exists():
            logger.warning(f"⚠️ Транзакция {trace_id} уже обработана.")
            return

        try:
            logger.info(f"🔍 Проверка пользователя по memo_phrase: {comment}")
            user = User.objects.filter(memo_phrase=comment).first()
            if not user:
                logger.warning(f"⚠️ Пользователь с memo_phrase {comment} не найден.")
                return

            logger.info(f"🔄 Получение символа токена для {asset_address}...")
            token_symbol = TransactionService.get_jetton_symbol(asset_address)
            if not token_symbol:
                logger.warning(f"⚠️ Не удалось определить символ токена для {asset_address}.")
                return

            logger.info(f"🔄 Поиск монеты {token_symbol} в базе...")
            coin = Coin.objects.filter(symbol=token_symbol).first()
            if not coin:
                logger.warning(f"⚠️ Коин {token_symbol} не найден в базе.")
                return

            amount = Decimal(int(amount)) / Decimal(1e9)
            logger.info(f"💰 Пополнение баланса пользователя {user.id} на {amount} {coin.symbol}.")

            user_balance, _ = UserBalance.objects.get_or_create(user=user, coin=coin, defaults={"amount": Decimal(0)})
            user_balance.amount += amount
            user_balance.save(update_fields=["amount"])

            transaction_id = str(uuid.uuid4())
            TransactionHistory.objects.create(
                user_balance=user_balance,
                amount=amount,
                type="arrival",
                subtype="deposit",
                trace_id=trace_id,
                transaction_id=transaction_id
            )

            logger.info(f"✅ Транзакция {trace_id} обработана. Баланс пользователя {user.id} пополнен на {amount} {coin.symbol}.")
        except IntegrityError as e:
            logger.error(f"❌ Ошибка базы данных при обработке транзакции {trace_id}: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"❌ Ошибка обработки транзакции {trace_id}: {e}", exc_info=True)

    @staticmethod
    def process_deposit():
        """Основной метод для обработки депозита."""
        transactions = TransactionService.fetch_transactions()

        for action in transactions:
            logger.info(f"🔄 Начинаем обработку транзакции: {action.get('trace_id')}")
            TransactionService.process_transaction(action)