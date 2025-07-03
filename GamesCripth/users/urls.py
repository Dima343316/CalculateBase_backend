from django.urls import path
from users.views import (
    TelegramAuthView,
    redirect_view,
    AuthSuccessRedirectView, MemoPhraseView
)


urlpatterns = [

    path('telegram/auth/',
         TelegramAuthView.as_view(),
         name='telegram_auth'
         ),  # Обработка авторизации

    path('telegram/redirect/',
         redirect_view,
         name='telegram_callback'
         ),  # Виджет для авторизации

    path('auth/success/',
         AuthSuccessRedirectView.as_view(),
         name='auth_success'
         ),

    path('api/v1/memo-phrase/',
         MemoPhraseView.as_view(),
         name='memo-phrase'
         ),
]

__all__=()
