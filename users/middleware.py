from rest_framework.exceptions import PermissionDenied


class BlockArchivedUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user and user.is_authenticated:
            if not user.is_active or getattr(user, "archived", False):
                raise PermissionDenied("Пользователь заблокирован или архивирован.")
        return self.get_response(request)