from django import forms

from .models import Challenge


class ChallengeForm(forms.ModelForm):
    class Meta:
        model = Challenge
        fields = ['title', 'description', 'starts_at', 'ends_at']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Final Exam Grind', 'autofocus': True}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Whoever logs the longest non-stop session wins. Describe the rules.'}),
            'starts_at': forms.DateInput(attrs={'type': 'date'}),
            'ends_at': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get('starts_at')
        end = cleaned.get('ends_at')
        if start and end and end < start:
            self.add_error('ends_at', 'The end date can’t be before the start date.')
        return cleaned