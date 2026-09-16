import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Course(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='courses')
    title = models.CharField(max_length=120)
    link = models.URLField(max_length=300, blank=True, verbose_name='Course link')
    slug = models.SlugField(max_length=160, unique=True, blank=True, editable=False)
    notes = models.TextField(blank=True)
    start_date = models.DateField(default=timezone.now)
    # Set by the system on the day the done hours reach the total hours.
    end_date = models.DateField(null=True, blank=True)
    total_hours = models.FloatField(default=0, verbose_name='Course hours')
    # Tracked by the system from finished study sessions; do not edit by hand.
    hours_done = models.FloatField(default=0)
    is_public = models.BooleanField(default=True, verbose_name='Shareable by link')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.owner} — {self.title}'

    def save(self, *args, **kwargs):
        self.slug = self.make_unique_slug(self.slug)
        super().save(*args, **kwargs)

    @classmethod
    def make_unique_slug(cls, existing=None):
        if existing:
            return existing
        from django.utils.text import slugify
        return uuid.uuid4().hex[:10]

    def credits(self):
        """Hours earned from finished sessions, as tracked by the system."""
        return round(self.hours_done, 2)

    def progress(self):
        if self.total_hours <= 0:
            return None
        return min(100, round(self.credits() / self.total_hours * 100))

    def remaining_hours(self):
        return max(0, round(self.total_hours - self.credits(), 2))

    def is_active_course(self):
        """On the desk until the system decides it is done (end_date set)."""
        return self.end_date is None

    def mark_complete_if_done(self):
        """Called after a session is credited: decide the end date ourselves."""
        if self.end_date is None and self.total_hours > 0 and self.credits() >= self.total_hours:
            self.end_date = timezone.now().date()
            self.save()


class Roadmap(models.Model):
    """A group of courses that together lead to one goal."""
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='roadmaps')
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    slug = models.SlugField(max_length=160, unique=True, blank=True, editable=False)
    is_public = models.BooleanField(default=True, verbose_name='Shareable by link')
    forked_from = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='forks')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.slug = self.make_unique_slug(self.slug)
        super().save(*args, **kwargs)

    @classmethod
    def make_unique_slug(cls, existing=None):
        if existing:
            return existing
        return uuid.uuid4().hex[:10]

    def step_count(self):
        return len(self.steps.all())

    def total_planned_hours(self):
        return sum(step.planned_hours for step in self.steps.all())


class RoadmapCourse(models.Model):
    """An ordered course inside a roadmap."""
    roadmap = models.ForeignKey(Roadmap, on_delete=models.CASCADE, related_name='steps')
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, related_name='roadmap_memberships')
    position = models.PositiveIntegerField(default=0)
    course_title_override = models.CharField(max_length=120, blank=True, verbose_name='Course title')
    planned_hours = models.FloatField(default=0, verbose_name='Planned hours')
    link = models.URLField(max_length=300, blank=True, verbose_name='Course link')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', 'id']

    def __str__(self):
        return f'{self.display_title()} → {self.roadmap}'

    def display_title(self):
        return self.course_title_override or (self.course.title if self.course else 'Untitled course')