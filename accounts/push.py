import datetime as dt
import json
import logging

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from .models import Profile, PushSubscription

logger = logging.getLogger(__name__)


def push_configured():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def send_push(subscription, payload):
    """Deliver one payload. Returns True on success; drops dead subscriptions."""
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info=subscription.as_webpush(),
            data=json.dumps(payload),
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={'sub': settings.VAPID_SUBJECT},
            ttl=60 * 60 * 12,
        )
        return True
    except WebPushException as exc:
        status = getattr(exc.response, 'status_code', None)
        if status in (404, 410):
            subscription.delete()
        else:
            logger.warning('Web Push failed for %s: %s', subscription.pk, exc)
    except Exception:
        logger.exception('Web Push crashed for %s', subscription.pk)
    return False


def send_inactivity_reminders(now=None):
    """Push one reminder to every subscribed user away for INACTIVITY_PUSH_HOURS.

    A user gets a single reminder per absence: it is skipped while
    inactivity_push_sent_at is newer than last_seen, and returning to the site
    (which moves last_seen forward) re-arms it. Returns the number of users notified.
    """
    now = now or timezone.now()
    cutoff = now - dt.timedelta(hours=settings.INACTIVITY_PUSH_HOURS)
    due = (
        Profile.objects
        .filter(last_seen__isnull=False, last_seen__lte=cutoff, user__push_subscriptions__isnull=False)
        .distinct()
        .select_related('user')
    )
    payload = {
        'title': 'yalla zaker',
        'body': "Your desk misses you — it's been a while. Ready for a study session?",
        'url': reverse('dashboard'),
    }
    notified = 0
    for profile in due:
        sent = profile.inactivity_push_sent_at
        if sent and sent >= profile.last_seen:
            continue
        delivered = False
        for sub in PushSubscription.objects.filter(user_id=profile.user_id):
            delivered = send_push(sub, payload) or delivered
        if delivered:
            Profile.objects.filter(pk=profile.pk).update(inactivity_push_sent_at=now)
            notified += 1
    return notified
