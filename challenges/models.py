from django.conf import settings
from django.db import models
from django.utils import timezone


class Challenge(models.Model):
    title = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_challenges')
    starts_at = models.DateField(default=timezone.now)
    ends_at = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def is_active(self):
        today = timezone.now().date()
        return self.starts_at <= today <= self.ends_at


class ChallengeMember(models.Model):
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='joined_challenges')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['challenge', 'user'], name='unique_challenge_member')]
        ordering = ['joined_at']

    def __str__(self):
        return f'{self.user} in {self.challenge}'

    @staticmethod
    def member_stats(user, challenge):
        """Study time for a member inside the challenge window.

        Uses segment overlap with [starts_at 00:00, ends_at 23:59:59] so a
        session that straddles the window counts toward the in-window part.
        """
        from studysessions.models import StudySegment

        window_open = timezone.datetime.combine(challenge.starts_at, timezone.datetime.min.time()).replace(tzinfo=timezone.get_current_timezone())
        window_close = timezone.datetime.combine(challenge.ends_at, timezone.datetime.max.time()).replace(tzinfo=timezone.get_current_timezone())

        total_seconds = 0
        longest = 0
        for segment in StudySegment.objects.filter(
            session__user=user,
            session__status='finished',
        ).select_related('session'):
            start = max(segment.started_at, window_open)
            end = segment.ended_at or timezone.now()
            end = min(end, window_close)
            if end > start:
                total_seconds += (end - start).total_seconds()
        for session in user.study_sessions.filter(status='finished', ended_at__isnull=False):
            if session.ended_at >= window_open and session.started_at <= window_close:
                longest = max(longest, session.duration_seconds)
        return {
            'total_seconds': int(total_seconds),
            'longest_seconds': longest,
        }

    @staticmethod
    def leaderboard(challenge):
        rows = []
        for member in challenge.members.select_related('user').prefetch_related('user__study_sessions'):
            stats = ChallengeMember.member_stats(member.user, challenge)
            rows.append((member.user, stats['longest_seconds'], stats['total_seconds']))
        rows.sort(key=lambda r: (-r[1], -r[2], r[0].username))
        return rows