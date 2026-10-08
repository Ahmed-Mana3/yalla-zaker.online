"""Regression tests for the Take a Break action.

The break window must always be measured from the break that is running
*now* — never from the first break of the session — and every transition has
to leave the session with exactly one open study segment and at most one open
break.
"""

import datetime as dt

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from studysessions.models import StudySession

User = get_user_model()


class TakeBreakTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='breaker', password='password123')
        self.client = Client()
        self.client.login(username='breaker', password='password123')

    def start_session(self, target='45'):
        self.client.post(reverse('session_start'), {'target': target, 'course': ''})
        return StudySession.objects.get(user=self.user)

    def expire_break(self, session):
        """Push the running break past MAX_BREAK_MINUTES."""
        br = session.break_segments.get(ended_at__isnull=True)
        br.started_at = timezone.now() - dt.timedelta(minutes=settings.MAX_BREAK_MINUTES + 1)
        br.save()
        return br

    # ----------------------------------------------------------- transitions

    def test_take_break_pauses_and_resumes(self):
        session = self.start_session()

        response = self.client.post(reverse('session_pause'))
        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.status, StudySession.STATUS_PAUSED)
        self.assertEqual(session.break_segments.filter(ended_at__isnull=True).count(), 1)
        self.assertEqual(session.study_segments.filter(ended_at__isnull=True).count(), 0)

        response = self.client.post(reverse('session_resume'))
        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.status, StudySession.STATUS_ACTIVE)
        self.assertEqual(session.break_segments.filter(ended_at__isnull=True).count(), 0)
        self.assertEqual(session.study_segments.filter(ended_at__isnull=True).count(), 1)

    def test_second_break_closes_the_first(self):
        """A second break must never leave the first one running."""
        session = self.start_session()

        self.client.post(reverse('session_pause'))
        first = session.break_segments.get(ended_at__isnull=True)
        self.client.post(reverse('session_resume'))
        first.refresh_from_db()
        self.assertIsNotNone(first.ended_at, 'resuming must close the break that was started')

        self.client.post(reverse('session_pause'))
        session.refresh_from_db()

        open_breaks = session.break_segments.filter(ended_at__isnull=True)
        self.assertEqual(open_breaks.count(), 1)
        self.assertNotEqual(open_breaks.get().pk, first.pk)
        self.assertEqual(session.open_break.pk, open_breaks.get().pk)
        self.assertEqual(session.study_segments.filter(ended_at__isnull=True).count(), 0)

    def test_pausing_twice_keeps_one_open_break(self):
        session = self.start_session()
        self.client.post(reverse('session_pause'))
        self.client.post(reverse('session_pause'))

        session.refresh_from_db()
        self.assertEqual(session.status, StudySession.STATUS_PAUSED)
        self.assertEqual(session.break_segments.filter(ended_at__isnull=True).count(), 1)

        page = self.client.get(reverse('study'))
        self.assertContains(page, 'already on a break')

    def test_study_time_keeps_ticking_after_a_break(self):
        """Resuming must always leave an open study segment, or time stops."""
        session = self.start_session()
        seg = session.study_segments.get(ended_at__isnull=True)
        seg.started_at = timezone.now() - dt.timedelta(minutes=10)
        seg.save()

        self.client.post(reverse('session_pause'))
        self.client.post(reverse('session_resume'))
        session.refresh_from_db()

        self.assertEqual(session.status, StudySession.STATUS_ACTIVE)
        self.assertEqual(session.study_segments.filter(ended_at__isnull=True).count(), 1)
        self.assertGreaterEqual(session.study_seconds(), 10 * 60)

    # ------------------------------------------------------------ rendering

    def test_study_page_counts_down_the_running_break(self):
        """The lamp must count down *this* break, not the first one of the session."""
        session = self.start_session()
        self.client.post(reverse('session_pause'))
        first = session.break_segments.get(ended_at__isnull=True)
        self.client.post(reverse('session_resume'))
        self.client.post(reverse('session_pause'))

        session.refresh_from_db()
        running = session.open_break
        self.assertIsNotNone(running)

        # Make the first break unambiguous: five minutes older than the running one.
        first.started_at = running.started_at - dt.timedelta(minutes=5)
        first.save()

        page = self.client.get(reverse('study'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'data-paused-at')
        # The `date` filter renders in the active time zone, so compare in it too.
        self.assertContains(page, timezone.localtime(running.started_at).strftime('%Y-%m-%dT%H:%M:%S'))
        self.assertNotContains(page, timezone.localtime(first.started_at).strftime('%Y-%m-%dT%H:%M:%S'))

    def test_state_api_reports_the_running_break(self):
        session = self.start_session()
        self.client.post(reverse('session_pause'))
        self.client.post(reverse('session_resume'))
        self.client.post(reverse('session_pause'))
        session.refresh_from_db()

        payload = self.client.get(reverse('session_state_api')).json()
        self.assertEqual(payload['session']['status'], 'paused')
        self.assertEqual(payload['session']['paused_at'], session.open_break.started_at.isoformat())
        self.assertGreater(payload['session']['break_left'], 0)
        self.assertLessEqual(payload['session']['break_left'], settings.MAX_BREAK_MINUTES * 60)

    # --------------------------------------------------------------- expiry

    def test_resume_after_an_expired_break_ends_the_session(self):
        session = self.start_session()
        self.client.post(reverse('session_pause'))
        self.expire_break(session)

        response = self.client.post(reverse('session_resume'))
        self.assertEqual(response.status_code, 302)
        session.refresh_from_db()
        self.assertEqual(session.status, StudySession.STATUS_FINISHED)
        self.assertEqual(session.break_segments.filter(ended_at__isnull=True).count(), 0)

        page = self.client.get(reverse('study'))
        self.assertContains(page, 'Your break lasted too long')
        self.assertNotContains(page, 'Back at it.')

    def test_study_page_never_offers_resume_for_a_dead_session(self):
        session = self.start_session()
        self.client.post(reverse('session_pause'))
        self.expire_break(session)

        page = self.client.get(reverse('study'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Your break lasted too long')
        self.assertNotContains(page, 'id="btn-resume"')
        self.assertNotContains(page, 'id="btn-pause"')

    def test_state_api_announces_an_expired_break(self):
        """The 4s poll ends the session — the next page load must explain why."""
        session = self.start_session()
        self.client.post(reverse('session_pause'))
        self.expire_break(session)

        payload = self.client.get(reverse('session_state_api')).json()
        self.assertEqual(payload['session']['status'], 'finished')

        page = self.client.get(reverse('study'))
        self.assertContains(page, 'Your break lasted too long')

    def test_a_new_session_can_start_after_an_expired_break(self):
        session = self.start_session()
        self.client.post(reverse('session_pause'))
        self.expire_break(session)

        response = self.client.post(reverse('session_start'), {'target': '30', 'course': ''})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            StudySession.objects.filter(user=self.user, status=StudySession.STATUS_ACTIVE).count(),
            1,
        )
