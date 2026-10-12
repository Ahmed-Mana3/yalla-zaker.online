from django import forms
from django.utils import timezone

from challenges.models import Challenge

from .models import Room


class RoomForm(forms.ModelForm):
    challenge = forms.ModelChoiceField(
        queryset=Challenge.objects.none(), required=False, empty_label='Choose a challenge…')

    class Meta:
        model = Room
        fields = ['name', 'topic', 'visibility', 'challenge', 'capacity']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': 'e.g. Calculus night shift', 'autofocus': True, 'maxlength': 60}),
            'topic': forms.TextInput(attrs={'placeholder': 'e.g. Chapter 4 problem sets, phones away', 'maxlength': 140}),
            'visibility': forms.RadioSelect,
            'capacity': forms.NumberInput(attrs={'min': Room.MIN_CAPACITY, 'max': Room.MAX_CAPACITY}),
        }
        labels = {'name': 'Room name', 'topic': 'What are you working on? (optional)', 'capacity': 'Seats'}

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        # Only challenges the host is in and that have not finished: nobody
        # should be able to aim a room at a board they cannot see.
        today = timezone.localdate()
        qs = Challenge.objects.filter(members__user=user, ends_at__gte=today)
        if self.instance.pk and self.instance.challenge_id:
            qs = Challenge.objects.filter(pk=self.instance.challenge_id) | qs
        self.fields['challenge'].queryset = qs.distinct().order_by('title')
        self.fields['visibility'].choices = Room.VISIBILITY_CHOICES
        # Django's own min_value=0 validator wins over the widget attrs, so set these last.
        self.fields['capacity'].widget.attrs.update(min=Room.MIN_CAPACITY, max=Room.MAX_CAPACITY)
        self.fields['capacity'].help_text = f'{Room.MIN_CAPACITY}–{Room.MAX_CAPACITY} people, you included.'

    def clean_capacity(self):
        cap = self.cleaned_data['capacity']
        if not Room.MIN_CAPACITY <= cap <= Room.MAX_CAPACITY:
            raise forms.ValidationError(f'Pick between {Room.MIN_CAPACITY} and {Room.MAX_CAPACITY} seats.')
        if self.instance.pk and cap < self.instance.member_count:
            raise forms.ValidationError(
                f'{self.instance.member_count} people are already in — you can’t go below that.')
        return cap

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('visibility') in (Room.VIS_CHALLENGE, Room.VIS_BOTH):
            if not cleaned.get('challenge') and not self.has_error('challenge'):
                if self.fields['challenge'].queryset.exists():
                    self.add_error('challenge', 'Pick the challenge whose members can see this room.')
                else:
                    self.add_error('challenge', 'You’re not in a running challenge yet. Join one first, or pick another audience.')
        else:
            cleaned['challenge'] = None
        return cleaned


class GoalForm(forms.Form):
    goal = forms.CharField(max_length=80, required=False)
