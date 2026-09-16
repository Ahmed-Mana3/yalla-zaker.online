import datetime as dt

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    bio = models.CharField(max_length=200, blank=True)
    # The hue drives the avatar color so every user gets a stable identity.
    avatar_hue = models.PositiveSmallIntegerField(default=210)
    # Updated by OnlineStatusMiddleware whenever the user is active on the site.
    last_seen = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.user.username

    def is_online(self, now=None):
        """True when the user was active on the site within the online window."""
        if not self.last_seen:
            return False
        now = now or timezone.now()
        window = getattr(settings, 'ONLINE_WINDOW_MINUTES', 5)
        return now - self.last_seen <= dt.timedelta(minutes=window)


class Friendship(models.Model):
    STATUS_PENDING = 'pending'
    STATUS_ACCEPTED = 'accepted'
    STATUS_DECLINED = 'declined'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_ACCEPTED, 'Accepted'),
        (STATUS_DECLINED, 'Declined'),
    ]

    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_friend_requests')
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='received_friend_requests')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['from_user', 'to_user'], name='unique_friend_pair')
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.from_user} -> {self.to_user} ({self.status})'

    @staticmethod
    def friends_of(user):
        """Return all users accepted as a friend of `user`."""
        from django.contrib.auth import get_user_model
        return get_user_model().objects.filter(
            Q(sent_friend_requests__to_user=user, sent_friend_requests__status=Friendship.STATUS_ACCEPTED)
            | Q(received_friend_requests__from_user=user, received_friend_requests__status=Friendship.STATUS_ACCEPTED)
        ).distinct()

    @staticmethod
    def are_friends(a, b):
        return Friendship.objects.filter(
            Q(from_user=a, to_user=b) | Q(from_user=b, to_user=a),
            status=Friendship.STATUS_ACCEPTED,
        ).exists()

    @staticmethod
    def connection(a, b):
        """The active row between two users, regardless of direction."""
        return Friendship.objects.filter(
            Q(from_user=a, to_user=b) | Q(from_user=b, to_user=a)
        ).first()