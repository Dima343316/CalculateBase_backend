# import logging
# from rest_framework.authentication import SessionAuthentication
# from django.utils.timezone import now
# from django.contrib.auth import get_user_model
# from rest_framework.exceptions import AuthenticationFailed
#
#
# logger = logging.getLogger(__name__)
#
# User = get_user_model()
#
# class TelegramSessionAuthentication(SessionAuthentication):
#     """
#     Кастомная аутентификация, основанная на сессиях, с добавлением поддержки Telegram.
#     """
#     def authenticate(self, request):
#         """
#         Проверка сессии пользователя по Telegram.
#         """
#         telegram_user_id = request.session.get('telegram_user_id')
#
#         if not telegram_user_id:
#             logger.warning(f"User not authenticated via Telegram. IP: {request.META.get('REMOTE_ADDR')}")
#             raise AuthenticationFailed('User is not authenticated via Telegram.')
#
#         auth_time = request.session.get('auth_time')
#         if auth_time and (now() - auth_time).seconds > 3600:  # Сессия истекает через 1 час
#             logger.warning(f"Session expired for user {telegram_user_id}.")
#             raise AuthenticationFailed('Session expired. Please log in again.')
#
#         logger.info(f"Authenticated via Telegram: {telegram_user_id}")
#
#         try:
#             user = get_user_model().objects.get(telegram_id=telegram_user_id)
#         except get_user_model().DoesNotExist:
#             logger.warning(f"User with telegram_id {telegram_user_id} does not exist.")
#             raise AuthenticationFailed('Authentication failed. Please check your credentials.')
#
#         except Exception as e:
#             logger.error(f"Unexpected error during authentication: {str(e)}")
#             raise AuthenticationFailed('Internal server error.')
#
#         request.session.modified = True
#         request.session.save()
#
#         return (user, None)
#
#     def authenticate_header(self, request):
#         """
#         Этот метод необходим для обработки заголовков в DRF.
#         """
#         return 'Bearer'