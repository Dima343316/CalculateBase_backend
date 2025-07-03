

class AuditLogMixin:
    def log_action(self, user, action, module, obj, changes=None):
        from .models import AuditLog
        AuditLog.objects.create(
            user=user,
            action=action,
            module=module,
            object_repr=str(obj),
            changes=changes or {}
        )