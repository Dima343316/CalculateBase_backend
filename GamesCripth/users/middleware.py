from django.http import HttpResponseForbidden
import environ

env = environ.Env()
environ.Env.read_env()


ALLOWED_ADMIN_IPS = env.list("ALLOWED_ADMIN_IPS")

class AdminIPRestrictionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR'))
        ip = ip.split(',')[0]  # на случай если там список
        if request.path.startswith('/admin/'):
            if ip not in ALLOWED_ADMIN_IPS:
                return HttpResponseForbidden(f"Доступ запрещён: {ip}")
        return self.get_response(request)
