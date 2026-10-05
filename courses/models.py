import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
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
    # Set when this course was forked from someone else's course or roadmap step.
    forked_from = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='forks')
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

    def hours_spent(self):
        """Hours earned across every course in this roadmap."""
        return round(sum(step.hours_spent() for step in self.steps.all()), 2)

    def completed_count(self):
        """How many of the courses in this roadmap are finished."""
        return sum(1 for step in self.steps.all() if step.is_complete())

    def tracked_count(self):
        """How many courses are linked to a real, hour-tracking course."""
        return sum(1 for step in self.steps.all() if step.is_tracked())

    def progress(self):
        """Whole-roadmap progress as 0-100 — every course in the path counts once."""
        steps = list(self.steps.all())
        if not steps:
            return 0
        return round(sum(step.progress() or 0 for step in steps) / len(steps))


class RoadmapCourse(models.Model):
    """An ordered course inside a roadmap."""
    roadmap = models.ForeignKey(Roadmap, on_delete=models.CASCADE, related_name='steps')
    course = models.ForeignKey(Course, on_delete=models.SET_NULL, null=True, blank=True, related_name='roadmap_memberships')
    position = models.PositiveIntegerField(default=0)
    course_title_override = models.CharField(max_length=120, blank=True, verbose_name='Course title')
    planned_hours = models.FloatField(default=0, verbose_name='Planned hours')
    link = models.URLField(max_length=300, blank=True, verbose_name='Course link')
    # Manual progress for courses that are not linked to a trackable course yet.
    progress_percent = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text='Set by hand for roadmap-only courses. Linked courses report their own progress.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', 'id']

    def __str__(self):
        return f'{self.display_title()} → {self.roadmap}'

    def display_title(self):
        return self.course_title_override or (self.course.title if self.course else 'Untitled course')

    def is_tracked(self):
        """True once this step points at a course that logs hours."""
        return self.course_id is not None

    def progress(self):
        """This course's progress as 0-100: the linked course's, else the manual mark."""
        if self.course_id and self.course:
            return self.course.progress() or 0
        return min(100, max(0, self.progress_percent or 0))

    def hours_spent(self):
        """Hours earned on this course, from the linked course when there is one."""
        if self.course_id and self.course:
            return self.course.credits()
        return round((self.planned_hours or 0) * self.progress() / 100, 2)

    def is_complete(self):
        if self.course_id and self.course:
            return self.course.end_date is not None or (self.course.progress() or 0) >= 100
        return self.progress() >= 100

    def is_trackable(self):
        """Whether it is safe to show this step's progress to someone who is not the owner."""
        return bool(self.course_id and self.course and self.course.is_public)

    def course_progress(self):
        return self.progress() if self.is_trackable() else 0
