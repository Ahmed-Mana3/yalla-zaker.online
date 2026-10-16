from django import forms

from .models import Course, Roadmap, RoadmapCourse


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['kind', 'title', 'link', 'notes', 'start_date', 'total_hours', 'total_pages', 'is_public']
        widgets = {
            'kind': forms.RadioSelect(),
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Linear Algebra II', 'autofocus': True}),
            'link': forms.URLInput(attrs={'placeholder': 'https://… (the course or book page)', 'inputmode': 'url'}),
            'notes': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Syllabus, resources, weekly plan…'}),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'total_hours': forms.NumberInput(attrs={'step': '0.5', 'min': '0'}),
            'total_pages': forms.NumberInput(attrs={'step': '1', 'min': '0'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Neither target is mandatory on its own — clean() requires the one that
        # matches the chosen kind, so switching type never blocks on the other.
        self.fields['total_hours'].required = False
        self.fields['total_pages'].required = False
        # Radio is pre-selected in the UI; tolerate posts that omit it and treat
        # them as a plain course so older clients keep working.
        self.fields['kind'].required = False

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get('kind') or Course.KIND_COURSE
        cleaned['kind'] = kind
        if kind == Course.KIND_BOOK:
            pages = cleaned.get('total_pages') or 0
            if pages <= 0:
                self.add_error('total_pages', 'Enter how many pages the book has.')
        else:
            hours = cleaned.get('total_hours') or 0
            if hours <= 0:
                self.add_error('total_hours', 'Enter how many hours the course needs.')
        return cleaned


class RoadmapForm(forms.ModelForm):
    class Meta:
        model = Roadmap
        fields = ['title', 'description', 'is_public']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Full-Stack Developer Path', 'autofocus': True}),
            'description': forms.Textarea(attrs={'rows': 3, 'placeholder': 'One goal this roadmap leads to — languages, tools, level…'}),
        }


class RoadmapCourseForm(forms.ModelForm):
    class Meta:
        model = RoadmapCourse
        fields = ['course_title_override', 'planned_hours', 'link']
        widgets = {
            'course_title_override': forms.TextInput(attrs={'placeholder': 'Course title'}),
            'planned_hours': forms.NumberInput(attrs={'step': '0.5', 'min': '0'}),
            'link': forms.URLInput(attrs={'placeholder': 'https://… (the course page)', 'inputmode': 'url'}),
        }