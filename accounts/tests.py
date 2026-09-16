import datetime as dt

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from courses.models import Course, Roadmap, RoadmapCourse
from studysessions.models import StudySession

from .models import Friendship, Profile


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
        self.assertContains(response, '<span class="tag">offline</span>')

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
        self.assertContains(response, '1 course · 12h planned')


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