from django import forms
from .models import User


class SendInviteAdminForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["email", "name", "role"]