import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Friendship, Profile
from controlpanel.registry import REGISTRY_BY_KEY, get_spec
from challenges.models import Challenge, ChallengeMember
from courses.models import Course, Roadmap, RoadmapCourse
from studysessions.models import BreakSegment, StudySegment, StudySession

User = get_user_model()

REGISTRY_KEYS = tuple(REGISTRY_BY_KEY)


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
            {'user', 'profile', 'friendship', 'group', 'course', 'roadmap', 'roadmapcourse',
             'challenge', 'challengemember', 'studysession', 'studysegment', 'breaksegment'},
        )

    def test_every_app_model_is_registered(self):
        """No model in any installed app may be missing from the panel."""
        from django.apps import apps as django_apps
        from django.contrib.auth.models import Group, Permission, User

        from controlpanel.registry import REGISTRY_BY_KEY

        registered = {spec.model for spec in REGISTRY_BY_KEY.values()}
        app_models = {
            m for m in django_apps.get_models()
            if m._meta.app_label in {'accounts', 'courses', 'challenges', 'studysessions'}
        }
        self.assertEqual(app_models - registered, set())

        # Permissions are deliberately absent: they are generated from the
        # models above and readable through each model's own group page.
        self.assertNotIn(Permission, registered)
        self.assertTrue({User, Group} <= registered)

    def test_record_form_renders_for_every_model(self):
        """Add and edit screens must build for all 12 record types."""
        from controlpanel.registry import REGISTRY
        from accounts.models import Profile

        prof_user = User.objects.create_user('prof')
        instances = {
            'user': self.owner,
            # accounts.signals.ensure_profile makes one on every new account.
            'profile': Profile.objects.get(user=prof_user),
            'friendship': Friendship.objects.create(from_user=self.owner, to_user=User.objects.create_user('pal')),
            'course': self.course,
            'roadmap': Roadmap.objects.create(owner=self.owner, title='Path'),
            'roadmapcourse': RoadmapCourse.objects.create(roadmap=Roadmap.objects.first(), course=self.course),
            'challenge': self.challenge,
            'challengemember': ChallengeMember.objects.create(challenge=self.challenge, user=self.owner),
            'studysession': StudySession.objects.create(user=self.owner, course=self.course),
            'studysegment': StudySegment.objects.create(session=StudySession.objects.first()),
            'breaksegment': BreakSegment.objects.create(session=StudySession.objects.first()),
            'group': None,
        }
        for spec in REGISTRY:
            with self.subTest(model=spec.key):
                add = self.client.get(reverse('controlpanel:record_add', args=[spec.key]))
                self.assertEqual(add.status_code, 200)
                obj = instances[spec.key]
                if obj is None:
                    continue
                edit = self.client.get(reverse('controlpanel:record_edit', args=[spec.key, obj.pk]))
                self.assertEqual(edit.status_code, 200)

    # ------------------------------------------------------------- minutes, not seconds

    def test_session_table_shows_minutes_not_seconds(self):
        session = StudySession.objects.create(
            user=self.owner, course=self.course,
            duration_seconds=5400, manual_seconds=1800,
        )
        spec = get_spec('studysession')
        cells = {c['field']: c['value'] for c in spec.row_cells(session)}
        self.assertEqual(cells['duration_seconds'], 90)
        self.assertEqual(cells['manual_seconds'], 30)

    def test_session_form_writes_minutes_into_seconds(self):
        session = StudySession.objects.create(user=self.owner, course=self.course)
        res = self.client.post(
            reverse('controlpanel:record_edit', args=['studysession', session.pk]),
            {
                'user': self.owner.pk,
                'course': self.course.pk,
                'status': 'finished',
                'started_at': '2026-02-01T10:00',
                'duration_seconds': '45',
                'manual_seconds': '20',
                'target_minutes': '60',
            },
        )
        self.assertEqual(res.status_code, 302, getattr(res, 'context', {}) and res.context['form'].errors)
        session.refresh_from_db()
        self.assertEqual(session.duration_seconds, 2700)
        self.assertEqual(session.manual_seconds, 1200)
        self.assertEqual(session.target_minutes, 60)

    def test_session_edit_form_prefills_minutes(self):
        session = StudySession.objects.create(
            user=self.owner, course=self.course, duration_seconds=3660,
        )
        res = self.client.get(reverse('controlpanel:record_edit', args=['studysession', session.pk]))
        self.assertContains(res, 'value="61"')

    def test_segment_rows_show_minutes(self):
        session = StudySession.objects.create(user=self.owner, course=self.course)
        seg = StudySegment.objects.create(
            session=session,
            started_at=timezone.now() - dt.timedelta(minutes=25),
            ended_at=timezone.now(),
        )
        spec = get_spec('studysegment')
        cells = {c['field']: c['value'] for c in spec.row_cells(seg)}
        self.assertEqual(cells['minutes'], 25)

    def test_no_second_columns_are_exposed(self):
        """No column may display a raw seconds count."""
        from controlpanel.registry import REGISTRY

        for spec in REGISTRY:
            for col in spec.columns:
                if col.field.endswith('_seconds'):
                    with self.subTest(model=spec.key, column=col.field):
                        self.assertEqual(col.kind, 'minutes')

    # ------------------------------------------------------------- safety

    def test_unlock_ignores_offsite_next(self):
        with self.settings(EXCLUSIVE_ADMIN_KEY='letmein'):
            res = self.client.post(
                f'{reverse("controlpanel:unlock")}?next=https://evil.example/steal',
                {'key': 'letmein', 'next': 'https://evil.example/steal'},
            )
            self.assertEqual(res.status_code, 302)
            self.assertEqual(res.url, reverse('controlpanel:dashboard'))

    def test_toggle_ignores_offsite_next(self):
        url = reverse('controlpanel:toggle_flag', args=['course', self.course.pk, 'is_public'])
        res = self.client.post(url, {'next': 'https://evil.example/'})
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.url, reverse('controlpanel:records', args=['course']))

    def test_lock_rejects_get(self):
        with self.settings(EXCLUSIVE_ADMIN_KEY='letmein'):
            self.assertEqual(self.client.get(reverse('controlpanel:lock')).status_code, 405)

    def test_search_keeps_context_after_write(self):
        url = reverse('controlpanel:record_add', args=['course'])
        res = self.client.post(f'{url}?q=Algebra', {
            'owner': self.owner.pk,
            'title': 'Physics',
            'start_date': '2026-02-01',
            'total_hours': '3',
            'hours_done': '0',
            'is_public': 'on',
        })
        self.assertEqual(res.status_code, 302)
        self.assertIn('q=Algebra', res.url)

    def test_bulk_delete_preview_shows_cascade(self):
        ChallengeMember.objects.create(challenge=self.challenge, user=self.owner)
        res = self.client.post(reverse('controlpanel:bulk_delete', args=['challenge']), {
            'pks': [str(self.challenge.pk)],
        })
        self.assertContains(res, 'This cascades')
        self.assertContains(res, 'will be deleted with it')

    def test_course_delete_reports_detached_sessions(self):
        session = StudySession.objects.create(user=self.owner, course=self.course)
        res = self.client.get(reverse('controlpanel:record_delete', args=['course', self.course.pk]))
        self.assertContains(res, 'survive')
        self.assertContains(res, 'study sessions')

    def test_records_table_query_count_does_not_grow_with_rows(self):
        """Rendering 20 rows must not cost more queries than rendering 1.

        Without select_related, each row's user and course columns fire their
        own query, so the count climbs with the page size.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        url = reverse('controlpanel:records', args=['studysession'])
        # The sidebar's live counts are fixed overhead on every panel page.
        sidebar_overhead = len(REGISTRY_KEYS)

        def page_queries():
            with CaptureQueriesContext(connection) as ctx:
                res = self.client.get(url)
            self.assertEqual(res.status_code, 200)
            # A per-row lookup would be a plain SELECT on auth_user with no join;
            # the sidebar's COUNT(*) is the only other bare auth_user query.
            stray = [
                q['sql'][:120] for q in ctx.captured_queries
                if 'FROM "auth_user"' in q['sql'] and 'JOIN' not in q['sql'] and 'COUNT' not in q['sql']
            ]
            self.assertEqual(stray, [], 'a bare auth_user lookup means select_related is missing')
            return len(ctx.captured_queries) - sidebar_overhead

        StudySession.objects.create(user=self.owner, course=self.course)
        few = page_queries()

        for i in range(18):
            user = User.objects.create_user(f'probe{i}')
            course = Course.objects.create(owner=user, title=f'P{i}', total_hours=2)
            StudySession.objects.create(user=user, course=course)

        self.assertEqual(StudySession.objects.count(), 19)
        self.assertEqual(page_queries(), few)

    def test_panel_pages_do_not_run_duplicate_counts(self):
        """Sidebar and dashboard share one COUNT pass; the dashboard adds none."""
        from controlpanel.registry import REGISTRY

        with self.assertNumQueries(len(REGISTRY)):
            self.client.get(reverse('controlpanel:dashboard'))

    def test_dashboard_covers_every_registered_model(self):
        res = self.client.get(reverse('controlpanel:dashboard'))
        from controlpanel.registry import REGISTRY

        for spec in REGISTRY:
            self.assertContains(res, spec.title)

    def test_numeric_search_finds_by_pk(self):
        target = Course.objects.create(owner=self.owner, title='Zzz', total_hours=1)
        res = self.client.get(reverse('controlpanel:records', args=['course']), {'q': str(target.pk)})
        self.assertContains(res, 'Zzz')
        self.assertContains(res, '1 record matching')

    def test_empty_search_does_not_match_everything(self):
        res = self.client.get(reverse('controlpanel:records', args=['course']), {'q': '   '})
        self.assertEqual(res.context['total'], Course.objects.count())

    def test_toggle_button_is_wired_into_the_table(self):
        res = self.client.get(reverse('controlpanel:records', args=['course']))
        toggle_url = reverse('controlpanel:toggle_flag', args=['course', self.course.pk, 'is_public'])
        self.assertContains(res, f'formaction="{toggle_url}"')
        self.assertContains(res, 'cp-flag--btn')

    def test_toggle_keeps_the_search_when_asked(self):
        url = reverse('controlpanel:toggle_flag', args=['course', self.course.pk, 'is_public'])
        res = self.client.post(url, {'next': f'{reverse("controlpanel:records", args=["course"])}?q=Alg'})
        self.assertEqual(res.status_code, 302)
        self.assertIn('q=Alg', res.url)

    def test_segments_have_readable_labels(self):
        session = StudySession.objects.create(user=self.owner, course=self.course)
        seg = StudySegment.objects.create(session=session)
        self.assertIn('study', str(seg))
        brk = BreakSegment.objects.create(session=session)
        self.assertIn('break', str(brk))

    def test_danger_notes_are_unique_and_set(self):
        from controlpanel.registry import REGISTRY

        for spec in REGISTRY:
            with self.subTest(model=spec.key):
                self.assertTrue(spec.danger.strip(), f'{spec.key} has no danger note')

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