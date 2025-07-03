from django.urls import path, include
from .views import SendInviteView, ConfirmInvitePage

urlpatterns = [
    path('invite/send/',
         SendInviteView.as_view(),
         name='send_invite'
         ),

    path('invite/confirm_page/<uuid:token>/',
         ConfirmInvitePage.as_view(),
         name='confirm_invite_page'
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
