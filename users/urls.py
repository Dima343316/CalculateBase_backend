from django.urls import path, include
from .views import SendInviteView, ConfirmInviteView


urlpatterns = [
    path('invite/send/',
         SendInviteView.as_view(),
         name='send_invite'
         ),

    path('invite/confirm/<uuid:token>/',
         ConfirmInviteView.as_view(),
         name='confirm_invite'
         ),
    path(
        "auth/",
        include("djoser.urls"
                )
    ),
    path(
        "auth/",
        include("djoser.urls.jwt")
    ),
]
