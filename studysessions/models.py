import datetime as dt

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone


class StudySession(models.Model):
    STATUS_ACTIVE = 'active'
    STATUS_PAUSED = 'paused'
    STATUS_FINISHED = 'finished'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Studying'),
        (STATUS_PAUSED, 'On a break'),
        (STATUS_FINISHED, 'Finished'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='study_sessions')
    course = models.ForeignKey('courses.Course', on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0)
    target_minutes = models.PositiveIntegerField(
        null=True, blank=True, help_text='Planned focus time in minutes. Empty means free focus (no timer).')
    checked_in = models.BooleanField(
        default=False, help_text='True once the post-session log prompt has been resolved.')
    manual_seconds = models.PositiveIntegerField(
        default=0, help_text='Study time the user confirmed and credited to the course.')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} {self.status} @ {self.started_at:%Y-%m-%d %H:%M}'

    # ------------------------------------------------------------------ utils

    def _open_study(self):
        return self.study_segments.filter(ended_at__isnull=True).first()

    def _open_break(self):
        return self.break_segments.filter(ended_at__isnull=True).first()

    def study_seconds(self):
        """Total study time across closed + open segments."""
        total = self.study_segments.filter(ended_at__isnull=False).aggregate(
            s=Sum(models.ExpressionWrapper(
                models.F('ended_at') - models.F('started_at'),
                output_field=models.DurationField())))['s'] or dt.timedelta(0)
        open_seg = self._open_study()
        if open_seg:
            total += timezone.now() - open_seg.started_at
        return int(total.total_seconds())

    def break_seconds(self):
        total = dt.timedelta(0)
        for br in self.break_segments.all():
            end = br.ended_at or timezone.now()
            total += end - br.started_at
        return total.total_seconds()

    @property
    def inline_minutes(self):
        """Default minutes for the post-session log prompt (min 1)."""
        return max(1, round(self.duration_seconds / 60))

    @property
    def clocked_hours(self):
        """Clocked focus time on the lamp in hours, rounded to 2 decimals."""
        return max(0.0, round(self.duration_seconds / 3600, 2))

    @property
    def manual_hours(self):
        """Course duration hours confirmed and credited by user."""
        return max(0.0, round(self.manual_seconds / 3600, 2))


    # ------------------------------------------------------------- lifecycle

    def refresh_lifecycle(self):
        """Enforce session expiration server-side.

        - A paused session whose break runs past MAX_BREAK_MINUTES is finished automatically.
        - An active session with a target_minutes whose focus time reached the target is finished.
        - A free-focus active session running over 12 hours is auto-finished.
        """
        if self.status == self.STATUS_ACTIVE:
            if self.target_minutes and self.study_seconds() >= self.target_minutes * 60:
                self.finish()
            elif self.study_seconds() >= 12 * 3600:
                self.finish()
            return self

        if self.status == self.STATUS_PAUSED:
            br = self._open_break()
            if not br:
                return self
            ceiling = timezone.now() - dt.timedelta(minutes=settings.MAX_BREAK_MINUTES)
            if br.started_at < ceiling:
                self.finish(force=True)
            return self

        return self


    def pause(self):
        if self.status != self.STATUS_ACTIVE:
            return False
        seg = self._open_study()
        if seg:
            seg.ended_at = timezone.now()
            seg.save()
        BreakSegment.objects.create(session=self)
        self.status = self.STATUS_PAUSED
        self.save()
        return True

    def resume(self):
        if self.status != self.STATUS_PAUSED:
            return 'noop'
        br = self._open_break()
        if not br:
            self.status = self.STATUS_ACTIVE
            self.save()
            return 'ok'
        expired = timezone.now() - br.started_at > dt.timedelta(minutes=settings.MAX_BREAK_MINUTES)
        if expired:
            self.finish(force=True)
            return 'ended'
        br.ended_at = timezone.now()
        br.save()
        StudySegment.objects.create(session=self)
        self.status = self.STATUS_ACTIVE
        self.save()
        return 'ok'

    def finish(self, force=False):
        if self.status == self.STATUS_FINISHED:
            return
        now = timezone.now()
        seg = self._open_study()
        if seg:
            seg.ended_at = now
            seg.save()
        br = self._open_break()
        if br:
            # A forced finish clamps the break to the allowed ceiling.
            br.ended_at = min(
                now,
                br.started_at + dt.timedelta(minutes=settings.MAX_BREAK_MINUTES),
            )
            br.save()
        self.duration_seconds = self.study_seconds()
        self.ended_at = now
        self.status = self.STATUS_FINISHED
        if not self.checked_in and self.course_id is None:
            self.checked_in = True
        self.save()

    def confirm_log(self, seconds):
        """Post-session check-in: the user confirms how much study to credit.

        The course is credited with exactly this amount (system time, not asks).
        Sessions without a course skip this entirely thanks to the views.
        """
        self.manual_seconds = seconds
        self.checked_in = True
        self.save()
        if self.course and seconds >= 60:
            self.course.hours_done += round(seconds / 3600, 2)
            self.course.save()
            self.course.mark_complete_if_done()

    # ---------------------------------------------------------------- queries

    def timed_out(self):
        """True while paused past the allowed break ceiling (finite window)."""
        if self.status != self.STATUS_PAUSED:
            return False
        br = self._open_break()
        if not br:
            return False
        return timezone.now() - br.started_at > dt.timedelta(minutes=settings.MAX_BREAK_MINUTES)

    @staticmethod
    def current_for(user):
        return StudySession.objects.filter(
            user=user, status__in=[StudySession.STATUS_ACTIVE, StudySession.STATUS_PAUSED]
        ).first()

    @classmethod
    def live_for(cls, user):
        """Return the genuinely active or paused session for a user.

        If a session has expired (e.g. target timer elapsed or break ran out),
        it is cleanly concluded server-side and None is returned.
        """
        session = cls.current_for(user)
        if not session:
            return None
        session.refresh_lifecycle()
        if session.status in [cls.STATUS_ACTIVE, cls.STATUS_PAUSED]:
            return session
        return None



class StudySegment(models.Model):
    session = models.ForeignKey(StudySession, on_delete=models.CASCADE, related_name='study_segments')
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['started_at']


class BreakSegment(models.Model):
    session = models.ForeignKey(StudySession, on_delete=models.CASCADE, related_name='break_segments')
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['started_at']