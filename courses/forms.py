from django import forms

from .models import Course, Roadmap, RoadmapCourse


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ['title', 'link', 'notes', 'start_date', 'total_hours', 'is_public']
        widgets = {
            'title': forms.TextInput(attrs={'placeholder': 'e.g. Linear Algebra II', 'autofocus': True}),
            'link': forms.URLInput(attrs={'placeholder': 'https://… (the course page)', 'inputmode': 'url'}),
            'notes': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Syllabus, resources, weekly plan…'}),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'total_hours': forms.NumberInput(attrs={'step': '0.5', 'min': '0'}),
        }


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