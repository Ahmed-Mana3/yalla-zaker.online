from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Friendship
from challenges.models import Challenge, ChallengeMember
from courses.models import Course, Roadmap, RoadmapCourse
from studysessions.models import StudySession

User = get_user_model()


class ControlPanelTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user('owner', 'o@example.com', 'pw-for-tests-1')
        self.course = Course.objects.create(owner=self.owner, title='Algebra', total_hours=10)
        self.challenge = Challenge.objects.create(
            created_by=self.owner,
            title='Sprint',
            starts_at='2026-01-01',
            ends_at='2026-01-31',
        )

    def test_dashboard_is_public(self):
        res = self.client.get(reverse('controlpanel:dashboard'))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Control panel')

    def test_list_view_is_public(self):
        res = self.client.get(reverse('controlpanel:records', args=['course']))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Algebra')

    def test_search_filters(self):
        url = reverse('controlpanel:records', args=['course'])
        self.assertContains(self.client.get(url, {'q': 'nope'}), 'No records match')

    def test_add_record(self):
        res = self.client.post(reverse('controlpanel:record_add', args=['course']), {
            'owner': self.owner.pk,
            'title': 'Chemistry',
            'link': '',
            'notes': '',
            'start_date': '2026-02-01',
            'total_hours': '12',
            'hours_done': '0',
            'is_public': 'on',
        })
        self.assertEqual(res.status_code, 302)
        self.assertTrue(Course.objects.filter(title='Chemistry').exists())

    def test_add_record_rejects_missing_fields(self):
        res = self.client.post(reverse('controlpanel:record_add', args=['course']), {'title': ''})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(Course.objects.filter(title='').exists())
        self.assertContains(res, 'This field is required')

    def test_delete_record(self):
        res = self.client.post(reverse('controlpanel:record_delete', args=['course', self.course.pk]))
        self.assertEqual(res.status_code, 302)
        self.assertFalse(Course.objects.filter(pk=self.course.pk).exists())

    def test_bulk_delete_asks_first(self):
        res = self.client.post(reverse('controlpanel:bulk_delete', args=['course']), {
            'pks': [str(self.course.pk)],
        })
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Delete 1 course?')
        self.assertTrue(Course.objects.filter(pk=self.course.pk).exists())

    def test_plural_for(self):
        from controlpanel.registry import get_spec

        spec = get_spec('course')
        self.assertEqual(spec.plural_for(1), '1 course')
        self.assertEqual(spec.plural_for(4), '4 courses')
        self.assertEqual(get_spec('roadmapcourse').plural_for(1), '1 roadmap step')
        self.assertEqual(get_spec('roadmapcourse').plural_for(2), '2 roadmap steps')

    def test_bulk_delete_confirmed(self):
        other = Course.objects.create(owner=self.owner, title='Physics', total_hours=5)
        res = self.client.post(reverse('controlpanel:bulk_delete', args=['course']), {
            'pks': [str(self.course.pk), str(other.pk)],
            'confirmed': '1',
        })
        self.assertEqual(res.status_code, 302)
        self.assertEqual(Course.objects.count(), 0)

    def test_bulk_delete_rejects_get(self):
        res = self.client.get(reverse('controlpanel:bulk_delete', args=['course']))
        self.assertEqual(res.status_code, 405)

    def test_toggle_flag(self):
        url = reverse('controlpanel:toggle_flag', args=['course', self.course.pk, 'is_public'])
        self.client.post(url)
        self.course.refresh_from_db()
        self.assertFalse(self.course.is_public)
        self.client.post(url)
        self.course.refresh_from_db()
        self.assertTrue(self.course.is_public)

    def test_toggle_flag_rejects_unknown_field(self):
        url = reverse('controlpanel:toggle_flag', args=['course', self.course.pk, 'title'])
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_duplicate_creates_a_new_record(self):
        url = reverse('controlpanel:duplicate', args=['course', self.course.pk])
        res = self.client.post(url)
        clone = Course.objects.exclude(pk=self.course.pk).get()
        self.assertRedirects(res, reverse('controlpanel:record_edit', args=['course', clone.pk]))
        self.assertEqual(clone.title, self.course.title)
        self.assertNotEqual(clone.slug, self.course.slug)

    def test_delete_view_renders_confirmation(self):
        res = self.client.get(reverse('controlpanel:record_delete', args=['course', self.course.pk]))
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Algebra')

    def test_unknown_model_is_404(self):
        self.assertEqual(self.client.get(reverse('controlpanel:records', args=['nope'])).status_code, 404)

    def test_edit_record(self):
        url = reverse('controlpanel:record_edit', args=['course', self.course.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.post(url, {
            'owner': self.owner.pk,
            'title': 'Algebra II',
            'link': '',
            'notes': '',
            'start_date': '2026-02-01',
            'total_hours': '10',
            'hours_done': '0',
            'is_public': 'on',
        })
        self.course.refresh_from_db()
        self.assertEqual(self.course.title, 'Algebra II')

    def test_user_password_is_hashed(self):
        self.client.post(reverse('controlpanel:record_add', args=['user']), {
            'username': 'newbie',
            'email': 'n@example.com',
            'password1': 'a-very-long-passphrase-9',
            'password2': 'a-very-long-passphrase-9',
        })
        created = User.objects.get(username='newbie')
        self.assertTrue(created.check_password('a-very-long-passphrase-9'))
        self.assertTrue(created.profile)

    def test_user_toggle_staff(self):
        url = reverse('controlpanel:record_edit', args=['user', self.owner.pk])
        self.client.post(url, {
            'username': self.owner.username,
            'email': self.owner.email,
            'is_active': 'on',
            'is_staff': 'on',
        })
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.is_staff)

    def test_every_registered_model_has_a_working_list(self):
        from controlpanel.registry import REGISTRY

        for spec in REGISTRY:
            with self.subTest(model=spec.key):
                self.assertEqual(self.client.get(reverse('controlpanel:records', args=[spec.key])).status_code, 200)

    def test_delete_user_cascades(self):
        Friendship.objects.create(from_user=self.owner, to_user=User.objects.create_user('b'))
        self.client.post(reverse('controlpanel:record_delete', args=['user', self.owner.pk]))
        self.assertFalse(User.objects.filter(pk=self.owner.pk).exists())
        self.assertFalse(ChallengeMember.objects.filter(challenge=self.challenge).exists())

    def test_models_covered(self):
        from controlpanel.registry import REGISTRY

        keys = {spec.key for spec in REGISTRY}
        self.assertEqual(
            keys,
            {'user', 'profile', 'friendship', 'course', 'roadmap', 'roadmapcourse',
             'challenge', 'challengemember', 'studysession', 'studysegment', 'breaksegment'},
        )

    def test_locked_when_key_configured(self):
        with self.settings(EXCLUSIVE_ADMIN_KEY='letmein'):
            url = reverse('controlpanel:dashboard')
            res = self.client.get(url)
            self.assertEqual(res.status_code, 302)
            self.assertIn(reverse('controlpanel:unlock'), res.url)
            self.assertEqual(self.client.get(url, follow=True).status_code, 200)
            self.client.post(f'{url}unlock/', {'key': 'wrong'})
            self.assertEqual(self.client.get(url).status_code, 302)
            self.client.post(f'{url}unlock/', {'key': 'letmein'})
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_unlock_hidden_when_no_key_configured(self):
        res = self.client.get(reverse('controlpanel:unlock'))
        self.assertRedirects(res, reverse('controlpanel:dashboard'))

    def test_lock_clears_the_passphrase(self):
        with self.settings(EXCLUSIVE_ADMIN_KEY='letmein'):
            url = reverse('controlpanel:dashboard')
            self.client.post(f'{url}unlock/', {'key': 'letmein'})
            self.client.post(reverse('controlpanel:lock'))
            self.assertEqual(self.client.get(url).status_code, 302)

    def test_pages_are_noindex(self):
        for name, args in [('controlpanel:dashboard', []), ('controlpanel:records', ['course'])]:
            with self.subTest(url=name):
                res = self.client.get(reverse(name, args=args))
                self.assertContains(res, 'noindex')
                self.assertNotContains(res, 'name="robots" content="index')