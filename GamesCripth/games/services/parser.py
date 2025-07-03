from games.services.transaction_service import TransactionService

def run_parser():
    """Основной метод парсера транзакций."""
    transactions = TransactionService.fetch_transactions()
    for action in transactions:
        TransactionService.process_transaction(action)

print(run_parser())