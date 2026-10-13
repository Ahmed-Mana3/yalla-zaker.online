import datetime as dt
import json
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from courses.models import Course, Roadmap, RoadmapCourse
from studysessions.models import StudySession

from .models import Friendship, Profile, PushSubscription
from .push import send_inactivity_reminders


class OnlineStatusTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='pw')
        self.bob = User.objects.create_user(username='bob', password='pw')
        Friendship.objects.create(from_user=self.alice, to_user=self.bob, status=Friendship.STATUS_ACCEPTED)

    def test_is_online_true_when_seen_recently(self):
        self.alice.profile.last_seen = timezone.now()
        self.alice.profile.save()
        self.assertTrue(self.alice.profile.is_online())

    def test_is_online_false_when_never_seen(self):
        self.assertFalse(self.alice.profile.is_online())

    def test_is_online_false_when_stale(self):
        self.alice.profile.last_seen = timezone.now() - dt.timedelta(minutes=10)
        self.alice.profile.save()
        self.assertFalse(self.alice.profile.is_online())

    def test_middleware_stamps_last_seen(self):
        self.client.force_login(self.alice)
        self.client.get('/dashboard/')
        self.alice.profile.refresh_from_db()
        self.assertIsNotNone(self.alice.profile.last_seen)

    def test_middleware_throttles_writes(self):
        self.client.force_login(self.alice)
        self.client.get('/dashboard/')
        self.alice.profile.refresh_from_db()
        first = self.alice.profile.last_seen
        self.client.get('/dashboard/')
        self.alice.profile.refresh_from_db()
        self.assertEqual(first, self.alice.profile.last_seen)

    def test_dashboard_sorts_online_friend(self):
        self.bob.profile.last_seen = timezone.now()
        self.bob.profile.save()
        self.client.force_login(self.alice)
        status = self.client.get('/dashboard/').context['friend_rows'][0]['status']
        self.assertEqual(status, 'online')

    def test_dashboard_label_offline_friend(self):
        self.client.force_login(self.alice)
        row = self.client.get('/dashboard/').context['friend_rows'][0]
        self.assertEqual(row['status'], 'offline')

    def test_dashboard_shows_studying_for_live_friend(self):
        StudySession.objects.create(user=self.bob, status=StudySession.STATUS_ACTIVE)
        self.client.force_login(self.alice)
        row = self.client.get('/dashboard/').context['friend_rows'][0]
        self.assertEqual(row['status'], 'live')

    def test_friends_page_marks_online_friend(self):
        self.bob.profile.last_seen = timezone.now()
        self.bob.profile.save()
        self.client.force_login(self.alice)
        response = self.client.get('/friends/')
        self.assertContains(response, 'status-online')
        self.assertContains(response, '>online</span>')

    def test_profile_page_offline_tag(self):
        self.client.force_login(self.alice)
        response = self.client.get(f'/users/{self.bob.username}/')
        self.assertContains(response, 'data-state="offline"')

    def test_profile_page_does_not_show_start_studying_button(self):
        Course.objects.create(owner=self.bob, title='Bob Public Course', total_hours=10, is_public=True)
        self.client.force_login(self.alice)
        response = self.client.get(f'/users/{self.bob.username}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bob Public Course')
        self.assertNotContains(response, 'Start studying')
        self.assertContains(response, 'Details')

    def test_own_profile_page_does_not_show_start_studying_button(self):
        Course.objects.create(owner=self.alice, title='Alice Public Course', total_hours=10, is_public=True)
        self.client.force_login(self.alice)
        response = self.client.get(f'/users/{self.alice.username}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alice Public Course')
        self.assertNotContains(response, 'Start studying')
        self.assertContains(response, 'Details')

    def test_dashboard_with_user_roadmap(self):
        rm = Roadmap.objects.create(owner=self.alice, title='Fullstack Track')
        RoadmapCourse.objects.create(roadmap=rm, position=1, course_title_override='Django Basics', planned_hours=12)
        self.client.force_login(self.alice)
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Fullstack Track')
        self.assertContains(response, '0/1 courses done · 0h')

    def test_dashboard_roadmap_sidebar_counts_finished_courses(self):
        rm = Roadmap.objects.create(owner=self.alice, title='Fullstack Track')
        RoadmapCourse.objects.create(roadmap=rm, position=0, course_title_override='Shipped', progress_percent=100)
        RoadmapCourse.objects.create(roadmap=rm, position=1, course_title_override='Todo')
        self.client.force_login(self.alice)
        response = self.client.get('/dashboard/')
        self.assertContains(response, '1/2 courses done')
        self.assertContains(response, '50%')

    def test_dashboard_has_no_roadmap_section_under_courses(self):
        Roadmap.objects.create(owner=self.alice, title='Fullstack Track')
        self.client.force_login(self.alice)
        response = self.client.get('/dashboard/')
        self.assertNotContains(response, 'desk-roadmaps-title')
        self.assertNotContains(response, 'class="d3-roadmaps"')
        self.assertContains(response, 'side-roadmaps-title')

    def test_dashboard_active_session_renders_focus_banner(self):
        course = Course.objects.create(owner=self.alice, title='Linear Algebra', total_hours=40)
        StudySession.objects.create(user=self.alice, course=course, status=StudySession.STATUS_ACTIVE, target_minutes=30)
        self.client.force_login(self.alice)
        response = self.client.get('/dashboard/')
        self.assertContains(response, 'id="desk-ring"')
        self.assertContains(response, 'data-status="active"')
        self.assertContains(response, 'data-target="30"')
        self.assertContains(response, 'Linear Algebra')
        self.assertContains(response, 'Open Session')
        self.assertNotContains(response, 'Ready to focus?')


class FriendProfileStatsTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='pw')
        self.bob = User.objects.create_user(username='bob', password='pw')
        self.carol = User.objects.create_user(username='carol', password='pw')
        Friendship.objects.create(from_user=self.alice, to_user=self.bob, status=Friendship.STATUS_ACCEPTED)

    def test_friend_sees_total_study_time_and_course_progress(self):
        course = Course.objects.create(owner=self.bob, title='Physics', total_hours=10, hours_done=2.5, is_public=False)
        StudySession.objects.create(user=self.bob, course=course, status=StudySession.STATUS_FINISHED, duration_seconds=3600)
        self.client.force_login(self.alice)
        response = self.client.get(f'/users/{self.bob.username}/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<dd>1h 0m</dd>')
        self.assertContains(response, 'All time')
        self.assertContains(response, 'Physics')
        self.assertContains(response, '2.5h done / 10h course')
        self.assertContains(response, 'Courses')

    def test_friend_sees_all_courses_not_just_public(self):
        Course.objects.create(owner=self.bob, title='Secret Prep', total_hours=5, is_public=False)
        self.client.force_login(self.alice)
        self.assertContains(
            self.client.get(f'/users/{self.bob.username}/'),
            'Secret Prep',
        )

    def test_stranger_does_not_see_stats_or_private_courses(self):
        Course.objects.create(owner=self.bob, title='Secret Prep', total_hours=5, is_public=False)
        Course.objects.create(owner=self.bob, title='Open Course', total_hours=5, is_public=True, hours_done=1)
        StudySession.objects.create(user=self.bob, status=StudySession.STATUS_FINISHED, duration_seconds=7200)
        self.client.force_login(self.carol)
        response = self.client.get(f'/users/{self.bob.username}/')
        self.assertContains(response, 'Open Course')
        self.assertNotContains(response, 'All time')
        self.assertNotContains(response, 'Secret Prep')

    def test_own_profile_shows_stats(self):
        Course.objects.create(owner=self.alice, title='Math', total_hours=10)
        StudySession.objects.create(user=self.alice, status=StudySession.STATUS_FINISHED, duration_seconds=5400)
        self.client.force_login(self.alice)
        response = self.client.get(f'/users/{self.alice.username}/')
        self.assertContains(response, '1h 30m')
        self.assertContains(response, 'All time')


class SeoTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(username='alice', password='pw')
        self.course = Course.objects.create(owner=self.alice, title='Linear Algebra', total_hours=40, is_public=True)
        self.client.raise_request_exception = True

    def test_robots_txt_served_plaintext(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertContains(response, 'User-agent: *')
        self.assertContains(response, 'Disallow: /admin/')
        self.assertContains(response, 'Sitemap:')

    def test_sitemap_includes_public_entries(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/xml')
        body = response.content.decode()
        self.assertIn('/signup/', body)
        self.assertIn(f'/{self.course.slug}/', body)
        self.assertIn(f'/users/{self.alice.username}/', body)

    def test_llms_txt_served(self):
        response = self.client.get('/llms.txt')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '# yalla zaker')
        self.assertContains(response, '/signup/')

    def test_canonical_and_description_on_public_pages(self):
        response = self.client.get('/')
        self.assertContains(response, 'rel="canonical"')
        self.assertContains(response, 'name="description"')
        self.assertContains(response, 'property="og:title"')
        self.assertContains(response, 'application/ld+json')

class InactivityPushTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='carol', password='pw')
        PushSubscription.objects.create(user=self.user, endpoint='https://push.example/abc', p256dh='k', auth='a')
        self.now = timezone.now()

    def _set_last_seen(self, hours):
        Profile.objects.filter(user=self.user).update(last_seen=self.now - dt.timedelta(hours=hours))

    def run_reminders(self):
        with mock.patch('accounts.push.send_push', return_value=True) as sender:
            return send_inactivity_reminders(self.now), sender

    def test_notifies_after_eight_hours_away(self):
        self._set_last_seen(9)
        count, sender = self.run_reminders()
        self.assertEqual(count, 1)
        self.assertEqual(sender.call_count, 1)

    def test_skips_recently_active_user(self):
        self._set_last_seen(7)
        count, sender = self.run_reminders()
        self.assertEqual(count, 0)
        sender.assert_not_called()

    def test_only_one_reminder_per_absence(self):
        self._set_last_seen(9)
        self.run_reminders()
        count, sender = self.run_reminders()
        self.assertEqual(count, 0)
        sender.assert_not_called()

    def test_returning_user_is_rearmed(self):
        self._set_last_seen(9)
        self.run_reminders()
        self._set_last_seen(8.5)  # visited after the reminder, then left again
        Profile.objects.filter(user=self.user).update(inactivity_push_sent_at=self.now - dt.timedelta(hours=10))
        count, _ = self.run_reminders()
        self.assertEqual(count, 1)

    def test_cron_endpoint_requires_secret(self):
        with self.settings(CRON_SECRET='s3cret'):
            self.assertEqual(self.client.get('/cron/inactivity-push/').status_code, 403)
            self.assertEqual(
                self.client.get('/cron/inactivity-push/', HTTP_AUTHORIZATION='Bearer nope').status_code, 403)

    def test_cron_endpoint_forbidden_when_secret_unset(self):
        with self.settings(CRON_SECRET=''):
            self.assertEqual(self.client.get('/cron/inactivity-push/', HTTP_AUTHORIZATION='Bearer ').status_code, 403)

    def test_cron_endpoint_runs_with_secret(self):
        self._set_last_seen(9)
        with self.settings(CRON_SECRET='s3cret', VAPID_PUBLIC_KEY='p', VAPID_PRIVATE_KEY='q'), \
                mock.patch('accounts.push.send_push', return_value=True):
            resp = self.client.get('/cron/inactivity-push/', HTTP_AUTHORIZATION='Bearer s3cret')
        self.assertEqual(resp.json(), {'ok': True, 'notified': 1})

    def test_subscribe_saves_and_unsubscribe_removes(self):
        self.client.login(username='carol', password='pw')
        body = {'endpoint': 'https://push.example/new', 'keys': {'p256dh': 'k2', 'auth': 'a2'}}
        resp = self.client.post('/push/subscribe/', json.dumps(body), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(PushSubscription.objects.filter(endpoint='https://push.example/new').exists())
        resp = self.client.post('/push/unsubscribe/', json.dumps({'endpoint': body['endpoint']}),
                                content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(PushSubscription.objects.filter(endpoint=body['endpoint']).exists())

    def test_subscribe_rejects_bad_payload_and_anonymous(self):
        self.assertEqual(self.client.post('/push/subscribe/', '{}', content_type='application/json').status_code, 302)
        self.client.login(username='carol', password='pw')
        self.assertEqual(self.client.post('/push/subscribe/', '{}', content_type='application/json').status_code, 400)
