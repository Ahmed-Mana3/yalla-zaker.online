"""Presence and focus-time numbers for a study room."""
import datetime as dt

from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from studysessions.models import StudySegment, StudySession

RANGE_TODAY = 'today'
RANGE_WEEK = 'week'
RANGES = [(RANGE_TODAY, 'Today'), (RANGE_WEEK, 'Last 7 days')]


def normalize_range(raw):
    return RANGE_WEEK if raw == RANGE_WEEK else RANGE_TODAY


def range_start(key):
    midnight = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    if key == RANGE_WEEK:
        return midnight - dt.timedelta(days=6)
    return midnight


def focus_seconds(user_ids, start):
    """{user_id: seconds studied since ``start``}, running sessions included."""
    now = timezone.now()
    totals = {uid: 0 for uid in user_ids}
    segments = StudySegment.objects.filter(session__user_id__in=user_ids).filter(
        Q(ended_at__isnull=True) | Q(ended_at__gt=start)
    ).values_list('session__user_id', 'started_at', 'ended_at')
    for uid, began, ended in segments:
        span = (ended or now) - max(began, start)
        if span.total_seconds() > 0:
            totals[uid] += int(span.total_seconds())
    return totals


def _presence(users):
    """{user_id: (status, label, running_session | None)} with expiry enforced."""
    live = {}
    for session in StudySession.objects.filter(
            user__in=users, status__in=[StudySession.STATUS_ACTIVE, StudySession.STATUS_PAUSED]):
        session.refresh_lifecycle()
        if session.status in (StudySession.STATUS_ACTIVE, StudySession.STATUS_PAUSED):
            live[session.user_id] = session
    out = {}
    for user in users:
        session = live.get(user.pk)
        profile = getattr(user, 'profile', None)
        if session and session.status == StudySession.STATUS_ACTIVE:
            out[user.pk] = ('live', 'studying now', session)
        elif session:
            out[user.pk] = ('paused', 'on a break', session)
        elif profile and profile.is_online():
            out[user.pk] = ('online', 'online', None)
        else:
            out[user.pk] = ('offline', 'offline', None)
    return out


def member_rows(room, viewer, range_key=RANGE_TODAY):
    """Ranked member rows. The room's own members only ever see each other."""
    members = list(room.members.select_related('user', 'user__profile'))
    users = [m.user for m in members]
    totals = focus_seconds([u.pk for u in users], range_start(range_key))
    presence = _presence(users)

    rows = []
    for m in members:
        status, label, session = presence[m.user_id]
        rows.append({
            'user': m.user,
            'goal': m.goal,
            'status': status,
            'label': label,
            'seconds': totals[m.user_id],
            # Seconds into the current focus block, for the live ticker.
            'elapsed': session.study_seconds() if status == 'live' else None,
            'is_owner': m.user_id == room.owner_id,
            'is_me': m.user_id == viewer.pk,
        })
    # Studying first only breaks ties; the ranking is about time put in.
    rows.sort(key=lambda r: (-r['seconds'], r['user'].username.lower()))
    for i, row in enumerate(rows, 1):
        row['rank'] = i
    return rows


def summarize(rows):
    return {
        'total_seconds': sum(r['seconds'] for r in rows),
        'studying': sum(1 for r in rows if r['status'] == 'live'),
        'on_break': sum(1 for r in rows if r['status'] == 'paused'),
        'online': sum(1 for r in rows if r['status'] == 'online'),
        'members': len(rows),
    }


def row_to_json(row):
    user = row['user']
    return {
        'username': user.username,
        'initial': user.username[:1].upper(),
        'hue': getattr(getattr(user, 'profile', None), 'avatar_hue', 210) or 210,
        'url': reverse('profile', kwargs={'username': user.username}),
        'goal': row['goal'],
        'status': row['status'],
        'label': row['label'],
        'seconds': row['seconds'],
        'elapsed': row['elapsed'],
        'rank': row['rank'],
        'is_owner': row['is_owner'],
        'is_me': row['is_me'],
    }
