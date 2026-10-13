from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Profile


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'autocomplete': 'email'}))

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']
        widgets = {
            'username': forms.TextInput(attrs={'autocomplete': 'username', 'autocapitalize': 'none'}),
            'password1': forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
            'password2': forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
            Profile.objects.get_or_create(user=user)
        return user


AVATAR_MAX_BYTES = 2 * 1024 * 1024
# Detected from file signatures, never from the client-supplied type.
AVATAR_SIGNATURES = [
    (b'\xff\xd8\xff', 'image/jpeg'),
    (b'\x89PNG\r\n\x1a\n', 'image/png'),
    (b'GIF87a', 'image/gif'),
    (b'GIF89a', 'image/gif'),
]


def sniff_image_type(head):
    for sig, ctype in AVATAR_SIGNATURES:
        if head.startswith(sig):
            return ctype
    if head[:4] == b'RIFF' and head[8:12] == b'WEBP':
        return 'image/webp'
    return None


class ProfileForm(forms.ModelForm):
    avatar = forms.FileField(
        required=False,
        label='Profile picture',
        widget=forms.ClearableFileInput(attrs={'accept': 'image/jpeg,image/png,image/gif,image/webp'}),
        help_text='JPG, PNG, GIF or WebP, up to 2 MB.',
    )
    remove_avatar = forms.BooleanField(required=False, label='Remove current picture')

    class Meta:
        model = Profile
        fields = ['bio']
        widgets = {'bio': forms.Textarea(attrs={'rows': 3, 'placeholder': 'What are you grinding on?'})}

    def clean_avatar(self):
        f = self.cleaned_data.get('avatar')
        if not f:
            return None
        if f.size > AVATAR_MAX_BYTES:
            raise forms.ValidationError('Picture is too large (max 2 MB).')
        data = f.read()
        ctype = sniff_image_type(data[:12])
        if not ctype:
            raise forms.ValidationError('Upload a JPG, PNG, GIF or WebP image.')
        return {'data': data, 'content_type': ctype}