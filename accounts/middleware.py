import datetime as dt

from django.conf import settings
from django.utils import timezone

from .models import Profile


class OnlineStatusMiddleware:
    """Stamp Profile.last_seen on authenticated requests, throttled.

    The timestamp is flushed to the database at most once per throttle
    window per session so a friend's presence stays fresh without a DB
    write on every single request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            self.mark_present(request)
        return self.get_response(request)

    def mark_present(self, request):
        now = timezone.now()
        throttle = dt.timedelta(seconds=getattr(settings, 'ONLINE_THROTTLE_SECONDS', 60))
        stamp_key = 'yz_last_seen'

        last = request.session.get(stamp_key)
        if last:
            try:
                last_dt = timezone.datetime.fromisoformat(last)
                if now - last_dt <= throttle:
                    return
            except (TypeError, ValueError):
                pass

        Profile.objects.filter(pk=request.user.pk).update(last_seen=now)
        request.session[stamp_key] = now.isoformat()