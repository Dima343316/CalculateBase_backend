from djoser.serializers import TokenCreateSerializer
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework.exceptions import AuthenticationFailed


class ForbiddenUserCreateSerializer(serializers.Serializer):
    def create(self, validated_data):
        raise serializers.ValidationError("Регистрация запрещена через API.")



class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        if not user.is_active:
            raise AuthenticationFailed('Аккаунт не активен.', code='user_inactive')

        if getattr(user, 'is_archived', False):
            raise AuthenticationFailed('Аккаунт архивирован.', code='user_archived')

        return data