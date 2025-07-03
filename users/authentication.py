from rest_framework import permissions
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed


class CsrfExemptSessionAuthentication(SessionAuthentication):
    def enforce_csrf(self, request):
        return


class CustomJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)

        if not user.is_active or getattr(user, "is_archived", False):
            raise AuthenticationFailed('Пользователь неактивен или архивирован')

        return user


class IsActiveAndNotArchived(BasePermission):
    message = 'Пользователь архивный или неактивный.'

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if not user.is_active or getattr(user, 'is_archived', False):
            return False
        return True