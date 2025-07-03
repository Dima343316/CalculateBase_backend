import asyncio
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.db.models import Count
from django.utils.timezone import now
from .models import (GameSession,
                     UserGameSession, Game)



class ActiveGamesConsumer(AsyncWebsocketConsumer):
    """WebSocket consumer для отправки списка активных игровых сессий в реальном времени."""

    async def connect(self):
        self.group_name = 'active_games'
        self.active = True

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Запуск цикла обновления
        asyncio.create_task(self.update_loop())

    async def disconnect(self, close_code):
        self.active = False
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def update_loop(self):
        while self.active:
            await self.send_active_games()
            await asyncio.sleep(1)

    async def send_active_games(self):
        active_sessions = await self.get_active_sessions()
        session_data = await self.get_sessions_with_player_counts(active_sessions)
        await self.send(text_data=json.dumps({"active_games": session_data}))

    @database_sync_to_async
    def get_active_sessions(self):
        return list(
            GameSession.objects.filter(
                status="active",
                end_time__gt=now()
            ).select_related("game")
        )

    @database_sync_to_async
    def get_player_counts(self, session_ids):
        player_counts = UserGameSession.objects.filter(game_session_id__in=session_ids) \
            .values("game_session_id") \
            .annotate(player_count=Count("id"))

        return {item["game_session_id"]: item["player_count"] for item in player_counts}

    @database_sync_to_async
    def get_supported_coins_for_game(self, game_id):
        game = Game.objects.get(id=game_id)
        # Извлекаем все связанные валюты для игры
        coins = game.supported_coins.all()
        return [coin.symbol for coin in coins]

    async def get_sessions_with_player_counts(self, sessions):
        session_ids = [session.id for session in sessions]
        player_counts = await self.get_player_counts(session_ids)

        sessions_by_game = {}

        for session in sessions:
            game = session.game
            game_id = game.id

            if game_id not in sessions_by_game:
                # Получаем список поддерживаемых валют для игры
                coin_symbols = await self.get_supported_coins_for_game(game_id)

                sessions_by_game[game_id] = {
                    "game_id": str(game.id),
                    "game_name": game.name,
                    "coin_symbols": coin_symbols,  # Валюты для игры
                    "cell_count": game.cell_count,
                    "sessions": []
                }

            sessions_by_game[game_id]["sessions"].append({
                "session_id": str(session.id),
                "end_time": session.end_time.isoformat(),
                "players": player_counts.get(session.id, 0),
                "remaining_time": max(0, int((session.end_time - now()).total_seconds()))
            })

        result = []
        for game_data in sessions_by_game.values():
            game_data["sessions"] = game_data["sessions"][:1]  # Ограничиваем до одного активного сеанса
            result.append(game_data)

        return result

    async def game_session_updated(self, event):
        await self.send_active_games()


__all__=()
