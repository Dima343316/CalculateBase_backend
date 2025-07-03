from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.db.models import Count, F, Sum
from datetime import timedelta
import time
import logging
from games.utils import is_integer
from users.models import User
from .models import (
    GameSession,
    GameSessionWinningCell,
    UserGameSession,
    UserBalance,
    TransactionHistory,
    Game
)
from celery import shared_task
from django.utils.timezone import now
from .utils import send_telegram_message


logger = logging.getLogger(__name__)

@shared_task
def finish_expired_game_sessions():
    """Завершает игровые сессии, у которых истекло время.
    Если есть пустые ячейки — игра отменяется и средства возвращаются.
    Если все ячейки заняты — определяется победитель по минимальному количеству ставок.
    """
    expired_sessions = GameSession.objects.filter(status="active", end_time__lte=now(), is_processing=False)

    for session in expired_sessions:
        session.is_processing = True
        session.save()

        try:
            with transaction.atomic():
                user_game_sessions = UserGameSession.objects.filter(game_session=session)

                if not user_game_sessions.exists():
                    session.status = "finished"
                    session.save()
                    GameSession.objects.create(
                        game=session.game,
                        start_time=now(),
                        end_time=now() + timedelta(seconds=session.game.game_time),
                        status="active",
                        commission_percent=session.game.commission_percent,
                        total_bet_amount=0.0,
                        commission_amount=0.0,
                    )
                    continue

                unique_users = user_game_sessions.values("user").distinct().count()
                first_user_session = user_game_sessions.first()
                coin = getattr(first_user_session, "coin", None)

                if not coin:
                    logger.error(f"Ошибка: не удалось определить валюту для сессии {session.id}.")
                    continue

                # ✅ Проверка: если только один игрок — возврат
                if unique_users == 1:
                    single_user = first_user_session.user
                    user_balance = UserBalance.objects.get(user=single_user, coin=coin)
                    total_refund = user_game_sessions.aggregate(total_bet=Sum("bet_amount"))["total_bet"] or 0.0

                    user_balance.amount += total_refund
                    user_balance.save()

                    TransactionHistory.objects.create(
                        user_balance=user_balance,
                        amount=total_refund,
                        type="arrival",
                        subtype="refund",
                        related_game_session=session,
                    )

                    if single_user.telegram_id:
                        refund_str = f"{total_refund:.0f} {coin.symbol}" if is_integer(total_refund) else f"{total_refund:g} {coin.symbol}"
                        send_telegram_message(single_user.telegram_id, f"ℹ️ Игра была отменена. Вам возвращено {refund_str}.")

                    session.status = "finished"
                    session.save()
                    user_game_sessions.update(status="finished", result='refund')
                    continue

                # ✅ Проверка на пустые ячейки
                used_cells = set(user_game_sessions.values_list("cell_number", flat=True))
                all_cells = set(range(1, session.game.cell_count + 1))
                empty_cells = all_cells - used_cells

                if empty_cells:
                    logger.info(f"Игра {session.id}: пустые ячейки {empty_cells}, игра отменена, деньги возвращены.")

                    for user_session in user_game_sessions:
                        user = user_session.user
                        user_balance = UserBalance.objects.get(user=user, coin=user_session.coin)
                        user_balance.amount += user_session.bet_amount
                        user_balance.save()

                        TransactionHistory.objects.create(
                            user_balance=user_balance,
                            amount=user_session.bet_amount,
                            type="arrival",
                            subtype="refund",
                            related_game_session=session,
                        )

                        if user.telegram_id:
                            refund_str = f"{user_session.bet_amount:.0f} {coin.symbol}" if is_integer(user_session.bet_amount) else f"{user_session.bet_amount:g} {coin.symbol}"
                            send_telegram_message(
                                user.telegram_id,
                                f"ℹ️ Игра была отменена,  Вам возвращено {refund_str}."
                            )

                    user_game_sessions.update(result='refund', status='finished')
                    session.status = "finished"
                    session.save()
                    continue

                # ✅ Продолжение — стандартный процесс определения победителей
                cell_counts = (
                    user_game_sessions
                    .values("cell_number")
                    .annotate(player_count=Count("id"))
                    .order_by("player_count")
                )

                min_count = cell_counts[0]["player_count"]
                winning_cells = [cell["cell_number"] for cell in cell_counts if cell["player_count"] == min_count]

                GameSessionWinningCell.objects.bulk_create([
                    GameSessionWinningCell(game_session=session, cell_number=cell) for cell in winning_cells
                ])

                winners = user_game_sessions.filter(cell_number__in=winning_cells)
                total_bet = user_game_sessions.aggregate(total_bet=Sum("bet_amount"))["total_bet"] or 0.0
                commission = total_bet * (session.commission_percent / 100)
                prize_pool = total_bet - commission

                if winners.exists() and prize_pool > 0:
                    total_winner_bets = sum(winner.bet_amount for winner in winners)
                    prize_per_winner = prize_pool / total_winner_bets

                    user_balances = {}

                    for winner in winners:
                        if not TransactionHistory.objects.filter(
                            user_balance__user=winner.user,
                            related_game_session=session,
                            related_user_game_session=winner
                        ).exists():
                            user_prize = prize_per_winner * winner.bet_amount
                            user_prize_str = f"{user_prize:.0f} {coin}" if is_integer(user_prize) else f"{user_prize:g} {coin}"

                            user_balance = user_balances.setdefault(
                                (winner.user, coin),
                                UserBalance.objects.get_or_create(user=winner.user, coin=coin)[0]
                            )
                            user_balance.amount += user_prize
                            user_balance.save()

                            TransactionHistory.objects.create(
                                user_balance=user_balance,
                                amount=user_prize,
                                type="arrival",
                                subtype="win",
                                related_game_session=session,
                                related_user_game_session=winner,
                            )

                            winner.result = 'win'
                            winner.save()

                            if winner.user.telegram_id:
                                send_telegram_message(
                                    winner.user.telegram_id,
                                    f"🎉 Поздравляем! Вы выиграли {user_prize_str}!"
                                )

                # ✅ Обработка проигравших
                winning_user_ids = set(winners.values_list("user_id", flat=True))
                losing_users = (
                    user_game_sessions
                    .exclude(user_id__in=winning_user_ids)
                    .values("user_id")
                    .distinct()
                )

                for entry in losing_users:
                    user_id = entry["user_id"]
                    user = User.objects.get(id=user_id)
                    loser_sessions = user_game_sessions.filter(user=user)

                    for loser_session in loser_sessions:
                        loser_session.result = 'lose'
                        loser_session.save()

                    if user.telegram_id:
                        total_user_bet = loser_sessions.aggregate(total=Sum("bet_amount"))["total"] or 0.0
                        bet_str = f"{total_user_bet:.0f} {coin}" if is_integer(total_user_bet) else f"{total_user_bet:g} {coin}"
                        send_telegram_message(user.telegram_id, f"😔 Вы проиграли. Ставка: {bet_str}. Удачи в следующей игре!")

                user_game_sessions.exclude(user_id__in=winning_user_ids).update(result='lose')
                user_game_sessions.update(status="finished")
                session.status = "finished"
                session.save()

        except Exception as e:
            logger.error(f"Ошибка при завершении сессии {session.id}: {str(e)}", exc_info=True)
            admin_user = User.objects.filter(is_staff=True).first()
            if admin_user and admin_user.telegram_id:
                send_telegram_message(
                    admin_user.telegram_id,
                    f"❌ Ошибка при завершении игровой сессии {session.id}. Проверьте логи."
                )

        finally:
            session.is_processing = False
            session.save()

@shared_task
def auto_start_games():
    """
    Автоматически запускает игровые сессии для всех активных игр.
    Новая сессия создается, если прошло заданное время после окончания последней сессии.
    """
    games = Game.objects.filter(status="active")
    if not games.exists():
        logger.warning("❌ Нет активных игр! Нечего запускать.")
        return

    logger.info(f"🔍 Найдено {games.count()} активных игр.")

    finished_sessions = GameSession.objects.filter(status="active", end_time__lte=now()).update(status="finished")
    if finished_sessions:
        logger.info(f"✅ Обновлено {finished_sessions} завершенных игровых сессий.")

    channel_layer = get_channel_layer()

    for game in games:
        last_session = GameSession.objects.filter(game=game, status="finished").order_by("-end_time").first()
        next_start_time = last_session.end_time if last_session else None
        auto_start_interval = game.auto_start_interval or 1  # Интервал в минутах

        if last_session:
            logger.info(f"🎮 Игра {game.name} (ID: {game.id}): последняя завершенная сессия {last_session.id}.")

        if not last_session or now() >= next_start_time + timedelta(minutes=auto_start_interval):
            try:
                with transaction.atomic():
                    game_session_in_progress = GameSession.objects.select_for_update().filter(
                        game=game, is_processing=True, status__in=["pending", "active"]
                    ).first()
                    if game_session_in_progress:
                        logger.info(f"🔄 Игра {game.name} (ID: {game.id}) - Сессия уже в процессе создания.")
                        continue

                    time.sleep(5)

                    new_session = GameSession.create_session(
                        game=game,
                        start_time=now(),
                        status="active"
                    )

                logger.info(f"✅ Создана новая игровая сессия {new_session.id} для {game.name}.")

                async_to_sync(channel_layer.group_send)(
                    "active_games",
                    {
                        "type": "game_session_updated",
                        "message": f"Game {game.id} has started!",
                        "session_id": str(new_session.id),
                    }
                )
            except Exception as e:
                logger.error(f"❌ Ошибка при создании игровой сессии для {game.name}: {e}", exc_info=True)
        else:
            wait_time = next_start_time + timedelta(minutes=auto_start_interval) - now()
            logger.info(f"🕒 Игра {game.name} (ID: {game.id}): ждать {wait_time}.")
