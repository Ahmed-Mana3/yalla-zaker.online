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

    # Set by refresh_lifecycle() when it auto-finishes this session during the
    # current request ('break', 'target' or 'overrun') so views can tell the
    # user why the session ended. Not persisted — it describes this request.
    expired_reason = None

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user} {self.status} @ {self.started_at:%Y-%m-%d %H:%M}'

    # ------------------------------------------------------------------ utils

    def _open_study(self):
        return self.study_segments.filter(ended_at__isnull=True).first()

    def _open_break(self):
        """The break running right now: the newest still-open segment.

        Stale open segments (if a request ever died mid-cycle) are older, so
        the newest one is always the clock to trust. pause/resume/finish close
        every leftover segment, so in practice there is only ever one.
        """
        return self.break_segments.filter(ended_at__isnull=True).order_by('-started_at').first()

    @property
    def open_break(self):
        """The running break, for templates and the state API.

        Never reach for ``break_segments.first`` in a template: that is the
        *first* break of the session, which is already closed once a second
        break is taken — a countdown built from it starts wrong and makes the
        client think the break is over (or already expired).
        """
        if self.status != self.STATUS_PAUSED:
            return None
        return self._open_break()

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

        When a session is finished here, ``expired_reason`` is set to 'break',
        'target' or 'overrun' so the views can explain it to the user.
        """
        if self.status == self.STATUS_ACTIVE:
            if self.target_minutes and self.study_seconds() >= self.target_minutes * 60:
                self.expired_reason = 'target'
                self.finish()
            elif self.study_seconds() >= 12 * 3600:
                self.expired_reason = 'overrun'
                self.finish()
            return self

        if self.status == self.STATUS_PAUSED:
            br = self._open_break()
            if not br:
                # Defensive: paused with no running break means the break row was
                # lost. Resume instead of freezing the session forever.
                self.resume()
                return self
            ceiling = timezone.now() - dt.timedelta(minutes=settings.MAX_BREAK_MINUTES)
            if br.started_at < ceiling:
                self.expired_reason = 'break'
                self.finish(force=True)
            return self

        return self


    def pause(self):
        """Take a break: close the study segment and open a break segment."""
        if self.status != self.STATUS_ACTIVE:
            return False
        now = timezone.now()
        # Close leftovers from an earlier cycle first, so exactly one study
        # segment and exactly one break segment are open afterwards. Without
        # this, a second break would leave the first one running and every
        # countdown/expiry check would key off a stale timestamp.
        self.study_segments.filter(ended_at__isnull=True).update(ended_at=now)
        self.break_segments.filter(ended_at__isnull=True).update(ended_at=now)
        BreakSegment.objects.create(session=self, started_at=now)
        self.status = self.STATUS_PAUSED
        self.save()
        return True

    def resume(self):
        """End the break and go back to studying.

        Returns 'ok', 'ended' (the break ran past MAX_BREAK_MINUTES) or
        'noop' (the session was not paused).
        """
        if self.status != self.STATUS_PAUSED:
            return 'noop'
        now = timezone.now()
        br = self._open_break()
        if br and now - br.started_at > dt.timedelta(minutes=settings.MAX_BREAK_MINUTES):
            self.expired_reason = 'break'
            self.finish(force=True)
            return 'ended'

        # Close every open break so break_seconds()/timed_out() stop ticking.
        for seg in self.break_segments.filter(ended_at__isnull=True):
            seg.ended_at = now
            seg.save()

        # Study time must never stop ticking: a segment left open while paused
        # is closed at the break start (so break time is not counted), and a
        # session with no open segment gets a fresh one.
        open_study = list(self.study_segments.filter(ended_at__isnull=True))
        if open_study:
            cut = br.started_at if br else now
            for seg in open_study:
                seg.ended_at = max(seg.started_at, cut)
                seg.save()
        else:
            StudySegment.objects.create(session=self, started_at=now)

        self.status = self.STATUS_ACTIVE
        self.save()
        return 'ok'

    def finish(self, force=False):
        if self.status == self.STATUS_FINISHED:
            return
        now = timezone.now()
        # Close *every* open segment: an orphaned one would keep counting time
        # on a finished session (and would make the next session look expired).
        self.study_segments.filter(ended_at__isnull=True).update(ended_at=now)
        for br in self.break_segments.filter(ended_at__isnull=True):
            # A break never counts past the allowed ceiling.
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

    def __str__(self):
        return f'{self.session_id} · study {self.started_at:%Y-%m-%d %H:%M}'

    @property
    def seconds(self):
        """Length in seconds; an open block measures up to now."""
        end = self.ended_at or timezone.now()
        return max(0, int((end - self.started_at).total_seconds()))

    @property
    def minutes(self):
        return max(0, round(self.seconds / 60))


class BreakSegment(models.Model):
    session = models.ForeignKey(StudySession, on_delete=models.CASCADE, related_name='break_segments')
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['started_at']

    def __str__(self):
        return f'{self.session_id} · break {self.started_at:%Y-%m-%d %H:%M}'

    @property
    def seconds(self):
        """Length in seconds; an open break measures up to now."""
        end = self.ended_at or timezone.now()
        return max(0, int((end - self.started_at).total_seconds()))

    @property
    def minutes(self):
        return max(0, round(self.seconds / 60))