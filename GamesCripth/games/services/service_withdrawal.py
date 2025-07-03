# services.py
import requests
from decimal import Decimal


TONSCAN_API_URL = "https://api.tonscan.io"  # Примерный URL для работы с TonScan API
SUPPORTED_COINS = {"TON": "TON", "USDT": "USD₮", "DOGS": "DOGS"}
MINIMUM_WITHDRAWAL = {
    "TON": Decimal('0.1'),
    "USDT": Decimal('10'),
    "DOGS": Decimal('50'),
}


class TransactionServiceWithdrawal:
    @staticmethod
    def get_user_balance(telegram_id, currency):
        try:
            response = requests.get(f"{TONSCAN_API_URL}/{currency}/balance?telegram_id={telegram_id}")
            response.raise_for_status()
            data = response.json()
            return data.get('balance', 0)
        except requests.RequestException as e:
            print(f"Ошибка при получении баланса: {e}")
            return 0

    @staticmethod
    def get_total_deposits(telegram_id, currency):
        try:
            response = requests.get(f"{TONSCAN_API_URL}/{currency}/deposits?telegram_id={telegram_id}")
            response.raise_for_status()
            data = response.json()
            total_deposit = sum([transaction['amount'] for transaction in data['transactions']])
            return total_deposit
        except requests.RequestException as e:
            print(f"Ошибка при получении депозитов: {e}")
            return 0

    @staticmethod
    def validate_transaction(user, amount, currency):
        # Проверяем минимальную сумму для вывода
        if amount < MINIMUM_WITHDRAWAL.get(currency, Decimal('0')):
            return False, f"Minimum withdrawal amount for {currency} is {MINIMUM_WITHDRAWAL[currency]}"

        # Получаем баланс пользователя
        user_balance = TransactionServiceWithdrawal.get_user_balance(user.telegram_id, currency)
        if user_balance < amount:
            return False, "Insufficient balance"

        # Получаем общую сумму депозитов пользователя
        total_deposits = TransactionServiceWithdrawal.get_total_deposits(user.telegram_id, currency)
        max_possible_win = total_deposits * 20  # Примерный коэффициент

        if amount > max_possible_win:
            return False, "Suspicious transaction: deposit limit exceeded"

        return True, "Transaction validated successfully"

