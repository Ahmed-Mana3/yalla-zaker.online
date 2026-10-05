"""Forms for the exclusive control panel.

Most record types get a form generated straight from the model metadata in
``registry``. Users get dedicated forms because the password fields are not
model fields and must never round-trip through a plain ModelForm.
"""

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.forms.models import modelform_factory

User = get_user_model()

WIDE_FIELDS = {'notes', 'description', 'bio', 'password1', 'password2', 'title', 'username',
               'email', 'link', 'first_name', 'last_name', 'course_title_override'}


def _widget_for(name, model_field):
    """Give date/time inputs the native pickers the rest of the site uses."""
    internal = model_field.get_internal_type()
    attrs = {'autocomplete': 'off'}
    if internal == 'DateField':
        return forms.DateInput(attrs={**attrs, 'type': 'date'})
    if internal == 'DateTimeField':
        return forms.DateTimeInput(attrs={**attrs, 'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M')
    if internal in ('FloatField', 'PositiveIntegerField', 'IntegerField', 'PositiveSmallIntegerField',
                    'SmallIntegerField'):
        return forms.NumberInput(attrs={**attrs, 'step': 'any'})
    if internal == 'TextField':
        return forms.Textarea(attrs={**attrs, 'rows': 4})
    if internal == 'URLField':
        return forms.URLInput(attrs={**attrs, 'inputmode': 'url', 'placeholder': 'https://…'})
    if internal == 'CharField' and model_field.choices:
        return forms.Select(attrs=attrs)
    if name in ('title', 'course_title_override'):
        return forms.TextInput(attrs={**attrs, 'placeholder': model_field.verbose_name.capitalize()})
    return None


_cache = {}


def form_class_for(spec, instance=None):
    """Build (and memoise) the form class for a spec.

    ``instance`` decides add vs edit, which only matters for the user model:
    creating needs a required password, editing treats it as optional.
    """
    if spec.special_form == 'user':
        return UserEditForm if instance is not None else UserCreateForm

    if spec.key in _cache:
        return _cache[spec.key]

    model = spec.model
    widgets = {}
    labels = {}
    helps = {}
    for name in spec.form_fields:
        model_field = model._meta.get_field(name)
        widget = _widget_for(name, model_field)
        if widget is not None:
            widgets[name] = widget
        labels[name] = model_field.verbose_name.capitalize()
        if model_field.help_text:
            helps[name] = model_field.help_text

    base = modelform_factory(
        model,
        fields=list(spec.form_fields),
        widgets=widgets,
        labels=labels,
        help_texts=helps,
    )
    cls = type(f'{model.__name__}PanelForm', (base,), {'wide_fields': WIDE_FIELDS})
    _cache[spec.key] = cls
    return cls


def form_for(spec, data=None, instance=None):
    return form_class_for(spec, instance=instance)(data=data, instance=instance)


# ------------------------------------------------------------------ users

class UserCreateForm(forms.ModelForm):
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text='At least 8 characters, not a common one.',
    )
    password2 = forms.CharField(
        label='Repeat password',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'is_superuser')
        labels = {
            'is_active': 'Active',
            'is_staff': 'Staff (can reach the Django admin)',
            'is_superuser': 'Superuser',
        }

    wide_fields = WIDE_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs['autofocus'] = True

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('That username is taken.')
        return username

    def clean_password2(self):
        p1 = self.cleaned_data.get('password1')
        p2 = self.cleaned_data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('The two passwords do not match.')
        validate_password(p2 or p1 or '')
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        user.save()
        from accounts.models import Profile
        Profile.objects.get_or_create(user=user)
        return user


class UserEditForm(forms.ModelForm):
    """Edit an account. A blank password leaves the current one in place."""

    new_password1 = forms.CharField(
        label='New password',
        required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text='Leave blank to keep the current password.',
    )
    new_password2 = forms.CharField(
        label='Repeat new password',
        required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'is_superuser')
        labels = {
            'is_active': 'Active',
            'is_staff': 'Staff (can reach the Django admin)',
            'is_superuser': 'Superuser',
        }

    wide_fields = WIDE_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['username'].disabled = True

    def clean_new_password2(self):
        p1 = self.cleaned_data.get('new_password1')
        p2 = self.cleaned_data.get('new_password2')
        if not p1 and not p2:
            return ''
        if p1 != p2:
            raise forms.ValidationError('The two passwords do not match.')
        validate_password(p2, self.instance)
        return p2

    def save(self, commit=True):
        user = super().save(commit=False)
        new_password = self.cleaned_data.get('new_password2')
        if new_password:
            user.set_password(new_password)
        user.save()
        return user