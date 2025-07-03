from django.urls import path
from django.urls import re_path

from . import views
from .consumers import ActiveGamesConsumer
from .views import (
    JoinGameSessionView,
    DepositFundsView,
    FinishGameSessionView,
    CheckUserBalanceView,
    GameDrawingStatsView,
    UserTransactionStatsView,
    TonTransactionsView,
    TransactionView,
    WithdrawalView, CoinBetLimitListView, MyWinsView, MyLossesView, LastDepositsView, LastWithdrawalsView,
    AvailableGamesByCoinView, show_qr_code, CoinContractAddressView
)

urlpatterns = [
    path(
        "api/v1/join-game-session/<uuid:game_uid>/",
        JoinGameSessionView.as_view(),
        name="join_game_session"
    ),
    path(
        "api/v1/deposit/",
        DepositFundsView.as_view(),
        name="deposit_funds"
    ),
    path(
        "api/v1/finish-game-session/<int:session_id>/",
        FinishGameSessionView.as_view(),
        name="finish_game_session"
    ),
    path(
        'api/v1/check_balance/',
        CheckUserBalanceView.as_view(),
        name='check_balance'
    ),
    path('api/v1/game-drawing-stats/<uuid:session_id>/',
         GameDrawingStatsView.as_view(),
         name='game_drawing_stats'
         ),
    path('api/v1/user-transaction-stats/',
         UserTransactionStatsView.as_view(),
         name='user_transaction_stats'
         ),
    path('api/v1/transactions/',
         TonTransactionsView.as_view(),
         name='transaction-list'
         ),
    path('api/v1/transaction/',
         TransactionView.as_view(),
         name='transaction'),

    path('api/v1/ton-transfer/',
         WithdrawalView.as_view(),
         name='ton_transfer'),

    path('api/v1/coin-bet-limits/',
         CoinBetLimitListView.as_view(),
         name='coin-bet-limits')
    ,
    path('api/v1/my-wins/',
         MyWinsView.as_view(),
         name='my_wins'
         ),
    path('api/v1/my-losses/',
         MyLossesView.as_view(),
         name='my_losses'
         ),
    path('admin/online-players/',
         views.admin_online_players,
         name='admin-online-players'
         ),
    path('api/v1/last-deposits/',
         LastDepositsView.as_view(),
         name='last_deposits'),

    path('api/v1/last-withdrawals/',
         LastWithdrawalsView.as_view(),
         name='last_withdrawals'),

    path('api/v1/last-withdrawals/',
         LastWithdrawalsView.as_view(),
         name='last_withdrawals'),

    path("api/available-games/<str:symbol>/",
         AvailableGamesByCoinView.as_view(),
         name="available-games-by-coin"
         ),
    path('qr/<str:symbol>/',
         show_qr_code,
         name='show_qr_code'
         ),
    path('coins/<str:symbol>/contract/',
         CoinContractAddressView.as_view(),
         name='coin-contract-address'
         ),

]

websocket_urlpatterns = [
    re_path(
        r"ws/active-games/$",
            ActiveGamesConsumer.as_asgi()
            ),
]



