import secrets

from django.conf import settings
from django.db import models
from django.db.models import Q

from accounts.models import Friendship
from challenges.models import ChallengeMember


def new_invite_token():
    # 12 random bytes -> 16 url-safe chars: unguessable, short enough to share.
    return secrets.token_urlsafe(12)


class Room(models.Model):
    VIS_FRIENDS = 'friends'
    VIS_CHALLENGE = 'challenge'
    VIS_BOTH = 'both'
    VIS_LINK = 'link'
    VISIBILITY_CHOICES = [
        (VIS_FRIENDS, 'Friends'),
        (VIS_CHALLENGE, 'Challenge members'),
        (VIS_BOTH, 'Friends and challenge members'),
        (VIS_LINK, 'Private link'),
    ]

    # Why somebody cannot join. Views turn these into friendly explanations.
    BLOCK_BANNED = 'banned'
    BLOCK_LOCKED = 'locked'
    BLOCK_FULL = 'full'
    BLOCK_NOT_FRIEND = 'not_friend'
    BLOCK_NOT_IN_CHALLENGE = 'not_in_challenge'
    BLOCK_NOT_IN_AUDIENCE = 'not_in_audience'
    BLOCK_LINK_ONLY = 'link_only'

    MIN_CAPACITY = 2
    MAX_CAPACITY = 50

    name = models.CharField(max_length=60)
    topic = models.CharField(
        max_length=140, blank=True,
        help_text='What this room is working on, so people know what they are walking into.')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_rooms')
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default=VIS_FRIENDS)
    challenge = models.ForeignKey(
        'challenges.Challenge', on_delete=models.SET_NULL, null=True, blank=True, related_name='rooms')
    invite_token = models.CharField(max_length=32, unique=True, default=new_invite_token, editable=False)
    capacity = models.PositiveSmallIntegerField(default=8)
    is_locked = models.BooleanField(default=False, help_text='A locked room accepts no new members.')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    # ------------------------------------------------------------- access

    def is_member(self, user):
        return user.is_authenticated and self.members.filter(user=user).exists()

    @property
    def member_count(self):
        return self.members.count()

    @property
    def is_full(self):
        return self.member_count >= self.capacity

    @property
    def includes_friends(self):
        return self.visibility in (self.VIS_FRIENDS, self.VIS_BOTH)

    @property
    def includes_challenge(self):
        return self.visibility in (self.VIS_CHALLENGE, self.VIS_BOTH)

    @property
    def audience_label(self):
        parts = []
        if self.includes_friends:
            parts.append(f'{self.owner.username}’s friends')
        if self.includes_challenge and self.challenge_id:
            parts.append(f'members of “{self.challenge.title}”')
        return ' and '.join(parts) or 'anyone with the link'

    def join_block(self, user, via_link=False):
        """None when ``user`` may join, otherwise one of the BLOCK_* codes.

        ``via_link`` means the person arrived through the invite link, which is
        the only credential a private-link room asks for. Friends and challenge
        rooms still check the relationship, so a leaked link opens nothing.
        """
        if user.pk == self.owner_id:
            return None
        if self.banned.filter(user=user).exists():
            return self.BLOCK_BANNED
        if self.visibility != self.VIS_LINK:
            is_friend = self.includes_friends and Friendship.are_friends(self.owner, user)
            in_challenge = self.includes_challenge and bool(self.challenge_id) and ChallengeMember.objects.filter(
                challenge_id=self.challenge_id, user=user).exists()
            if not (is_friend or in_challenge):
                return {
                    self.VIS_FRIENDS: self.BLOCK_NOT_FRIEND,
                    self.VIS_CHALLENGE: self.BLOCK_NOT_IN_CHALLENGE,
                }.get(self.visibility, self.BLOCK_NOT_IN_AUDIENCE)
        if self.visibility == self.VIS_LINK and not via_link:
            return self.BLOCK_LINK_ONLY
        if self.is_locked:
            return self.BLOCK_LOCKED
        if self.is_full:
            return self.BLOCK_FULL
        return None

    def regenerate_invite(self):
        self.invite_token = new_invite_token()
        self.save(update_fields=['invite_token'])

    # ------------------------------------------------------------ queries

    @classmethod
    def for_member(cls, user):
        return cls.objects.filter(members__user=user).select_related('owner', 'challenge').distinct()

    @classmethod
    def discoverable_for(cls, user):
        """Rooms the user could join without a link and has not joined yet."""
        friend_ids = Friendship.friends_of(user).values_list('pk', flat=True)
        my_challenges = ChallengeMember.objects.filter(user=user).values_list('challenge_id', flat=True)
        return (
            cls.objects
            .filter(is_locked=False)
            .filter(
                Q(visibility__in=[cls.VIS_FRIENDS, cls.VIS_BOTH], owner_id__in=list(friend_ids))
                | Q(visibility__in=[cls.VIS_CHALLENGE, cls.VIS_BOTH], challenge_id__in=list(my_challenges)))
            .exclude(members__user=user)
            .exclude(banned__user=user)
            .select_related('owner', 'challenge')
            .distinct()
        )


class RoomMember(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='room_memberships')
    goal = models.CharField(max_length=80, blank=True, help_text='What I am working on right now.')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['room', 'user'], name='unique_room_member')]
        ordering = ['joined_at']

    def __str__(self):
        return f'{self.user} in {self.room}'


class RoomBan(models.Model):
    """Removed by the owner. Without this a kicked person could simply re-join from the link."""
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='banned')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='room_bans')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['room', 'user'], name='unique_room_ban')]

    def __str__(self):
        return f'{self.user} banned from {self.room}'
