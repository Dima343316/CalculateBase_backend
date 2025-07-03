from django import forms
from .models import Game


class GameForm(forms.ModelForm):
    class Meta:
        model = Game
        fields = [
            'name',
            'cell_count',
            'status',
            'game_time',
            'commission_percent',
            'auto_start_interval',
            'supported_coins',  # добавим если нужно ManyToMany
        ]
        widgets = {
            'supported_coins': forms.CheckboxSelectMultiple,
        }

    def clean_game_time(self):
        game_time = self.cleaned_data['game_time']
        if game_time <= 0:
            raise forms.ValidationError("Время игры должно быть больше нуля (в секундах).")
        return game_time

    def clean_auto_start_interval(self):
        interval = self.cleaned_data['auto_start_interval']
        if interval < 1:
            raise forms.ValidationError("Интервал автостарта должен быть хотя бы 1 секунда.")
        return interval

__all__=()
