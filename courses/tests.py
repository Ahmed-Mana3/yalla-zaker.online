from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from courses.models import Course, Roadmap, RoadmapCourse

User = get_user_model()


class RoadmapTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='password123')
        self.other = User.objects.create_user(username='other', password='password123')
        self.client = Client()
        self.client.login(username='tester', password='password123')
        self.course_a = Course.objects.create(owner=self.user, title='Algebra I', total_hours=10.0, hours_done=2.0)
        self.course_b = Course.objects.create(owner=self.user, title='Algebra II', total_hours=20.0, hours_done=5.0)
        self.roadmap = Roadmap.objects.create(owner=self.user, title='Math Pathway', is_public=True)

    def test_roadmap_has_unique_slug(self):
        roadmap = Roadmap.objects.create(owner=self.user, title='Another Path')
        other_slug = Roadmap.objects.create(owner=self.user, title='Another Path')
        self.assertNotEqual(roadmap.slug, other_slug.slug)
        self.assertEqual(len(roadmap.slug), 10)

    def test_roadmap_create_view(self):
        response = self.client.post(reverse('roadmap_create'), {
            'title': 'Python to Web Dev',
            'description': 'One goal',
            'is_public': 'on',
        })
        roadmap = Roadmap.objects.get(title='Python to Web Dev')
        self.assertRedirects(response, reverse('roadmap_detail', kwargs={'slug': roadmap.slug}))
        self.assertEqual(roadmap.owner, self.user)

    def test_roadmap_detail_requires_owner(self):
        other_roadmap = Roadmap.objects.create(owner=self.other, title='Secret')
        response = self.client.get(reverse('roadmap_detail', kwargs={'slug': other_roadmap.slug}))
        self.assertEqual(response.status_code, 404)

    def test_add_course_appends_steps(self):
        response = self.client.post(reverse('roadmap_add_step', kwargs={'slug': self.roadmap.slug}), {
            'title': 'Operating Systems',
            'link': 'https://example.com/os',
            'planned_hours': '10',
        })
        self.assertRedirects(response, reverse('roadmap_steps_edit', kwargs={'slug': self.roadmap.slug}))
        self.client.post(reverse('roadmap_add_step', kwargs={'slug': self.roadmap.slug}), {
            'title': 'Networks',
            'link': 'https://example.com/net',
            'planned_hours': '15',
        })
        steps = list(RoadmapCourse.objects.filter(roadmap=self.roadmap).order_by('position'))
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].display_title(), 'Operating Systems')
        self.assertEqual(steps[1].display_title(), 'Networks')
        self.assertEqual(steps[0].position, 0)
        self.assertEqual(steps[1].position, 1)

    def test_remove_step_renumbers(self):
        s1 = RoadmapCourse.objects.create(roadmap=self.roadmap, course_title_override='Step A', position=0)
        RoadmapCourse.objects.create(roadmap=self.roadmap, course_title_override='Step B', position=1)
        self.client.post(reverse('roadmap_remove_step', kwargs={'slug': self.roadmap.slug, 'step_id': s1.id}))
        remaining = RoadmapCourse.objects.get(roadmap=self.roadmap)
        self.assertEqual(remaining.display_title(), 'Step B')
        self.assertEqual(remaining.position, 0)

    def test_reorder_view(self):
        s1 = RoadmapCourse.objects.create(roadmap=self.roadmap, course_title_override='Step A', position=0)
        s2 = RoadmapCourse.objects.create(roadmap=self.roadmap, course_title_override='Step B', position=1)
        response = self.client.post(reverse('roadmap_reorder', kwargs={'slug': self.roadmap.slug}), {
            'order': f'{s2.id},{s1.id}',
        })
        self.assertEqual(response.status_code, 200)
        s1.refresh_from_db()
        s2.refresh_from_db()
        self.assertEqual(s1.position, 1)
        self.assertEqual(s2.position, 0)

    def test_roadmap_total_planned_hours(self):
        RoadmapCourse.objects.create(roadmap=self.roadmap, course_title_override='Course A', planned_hours=10.0, position=0)
        RoadmapCourse.objects.create(roadmap=self.roadmap, course_title_override='Course B', planned_hours=20.0, position=1)
        self.assertEqual(self.roadmap.total_planned_hours(), 30.0)

    def test_public_roadmap_page(self):
        self.client.logout()
        RoadmapCourse.objects.create(roadmap=self.roadmap, course_title_override='Algebra I', position=0)
        response = self.client.get(reverse('public:roadmap_public', kwargs={'slug': self.roadmap.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Math Pathway')
        self.assertContains(response, 'Algebra I')

    def test_private_roadmap_page_hidden(self):
        self.roadmap.is_public = False
        self.roadmap.save()
        self.client.logout()
        response = self.client.get(reverse('public:roadmap_public', kwargs={'slug': self.roadmap.slug}))
        self.assertEqual(response.status_code, 404)

    def test_clone_roadmap_duplicates_all_courses(self):
        RoadmapCourse.objects.create(roadmap=self.roadmap, course_title_override='Algebra I', planned_hours=10.0, link='https://example.com/alg', position=0)
        RoadmapCourse.objects.create(roadmap=self.roadmap, course_title_override='Linear Algebra', planned_hours=12.0, link='https://example.com/lin', position=1)

        self.client.post(reverse('roadmap_clone', kwargs={'slug': self.roadmap.slug}))
        clone = Roadmap.objects.get(owner=self.user, forked_from=self.roadmap)
        steps = list(clone.steps.order_by('position'))
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].display_title(), 'Algebra I')
        self.assertEqual(steps[0].planned_hours, 10.0)
        self.assertEqual(steps[1].display_title(), 'Linear Algebra')
        self.assertEqual(steps[1].planned_hours, 12.0)

    def test_view_displays_roadmaps(self):
        response = self.client.get(reverse('roadmaps'))
        self.assertContains(response, 'Math Pathway')

    def test_add_course_to_roadmap(self):
        """A course is added directly to the roadmap."""
        response = self.client.post(reverse('roadmap_add_step', kwargs={'slug': self.roadmap.slug}), {
            'title': 'Operating Systems',
            'link': 'https://example.com/os',
            'planned_hours': '12',
        })
        self.assertRedirects(response, reverse('roadmap_steps_edit', kwargs={'slug': self.roadmap.slug}))
        step = RoadmapCourse.objects.get(roadmap=self.roadmap)
        self.assertEqual(step.display_title(), 'Operating Systems')
        self.assertEqual(step.planned_hours, 12.0)
        self.assertEqual(step.link, 'https://example.com/os')
        self.assertEqual(step.position, 0)
        self.assertIsNone(step.course)

    def test_add_course_requires_title_and_link(self):
        for payload in ({'title': '   ', 'link': 'https://example.com/x'}, {'title': 'Robotics', 'link': '   '}):
            response = self.client.post(reverse('roadmap_add_step', kwargs={'slug': self.roadmap.slug}), payload)
            self.assertRedirects(response, reverse('roadmap_steps_edit', kwargs={'slug': self.roadmap.slug}))
            self.assertFalse(RoadmapCourse.objects.filter(roadmap=self.roadmap).exists())

    def test_edit_course_title_hours_and_link(self):
        step = RoadmapCourse.objects.create(
            roadmap=self.roadmap, course=None, course_title_override='Old name',
            planned_hours=4, link='https://example.com/old', position=0)
        response = self.client.post(reverse('roadmap_edit_step', kwargs={'slug': self.roadmap.slug, 'step_id': step.id}), {
            'course_title_override': 'New name',
            'planned_hours': '9.5',
            'link': 'https://example.com/new',
        })
        self.assertRedirects(response, reverse('roadmap_steps_edit', kwargs={'slug': self.roadmap.slug}))
        step.refresh_from_db()
        self.assertEqual(step.display_title(), 'New name')
        self.assertEqual(step.planned_hours, 9.5)
        self.assertEqual(step.link, 'https://example.com/new')

    def test_roadmap_steps_edit_view(self):
        RoadmapCourse.objects.create(roadmap=self.roadmap, course_title_override='Deep Learning', position=0)
        response = self.client.get(reverse('roadmap_steps_edit', kwargs={'slug': self.roadmap.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Edit steps')
        self.assertContains(response, 'Course Sequence')
        self.assertContains(response, 'Deep Learning')

    def test_roadmap_add_step_ajax(self):
        response = self.client.post(
            reverse('roadmap_add_step', kwargs={'slug': self.roadmap.slug}),
            {'title': 'AJAX Course', 'link': 'https://example.com/ajax', 'planned_hours': '6'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['step']['title'], 'AJAX Course')
        self.assertEqual(data['step']['planned_hours'], 6.0)

    def test_roadmap_edit_step_ajax(self):
        step = RoadmapCourse.objects.create(roadmap=self.roadmap, course=None, course_title_override='Old', position=0)
        response = self.client.post(
            reverse('roadmap_edit_step', kwargs={'slug': self.roadmap.slug, 'step_id': step.id}),
            {'course_title_override': 'New AJAX', 'planned_hours': '3', 'link': 'https://example.com/edit'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['step']['title'], 'New AJAX')

    def test_roadmap_remove_step_ajax(self):
        step = RoadmapCourse.objects.create(roadmap=self.roadmap, course=None, course_title_override='To Delete', position=0)
        response = self.client.post(
            reverse('roadmap_remove_step', kwargs={'slug': self.roadmap.slug, 'step_id': step.id}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])
        self.assertEqual(data['step_id'], step.id)
        self.assertFalse(RoadmapCourse.objects.filter(id=step.id).exists())


class RoadmapProgressTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='walker', password='password123')
        self.other = User.objects.create_user(username='stranger', password='password123')
        self.client = Client()
        self.client.login(username='walker', password='password123')
        self.roadmap = Roadmap.objects.create(owner=self.user, title='Systems Path', is_public=True)
        self.tracked = RoadmapCourse.objects.create(
            roadmap=self.roadmap, course=None, course_title_override='Operating Systems',
            planned_hours=20.0, link='https://example.com/ostep', position=0)
        self.plain = RoadmapCourse.objects.create(
            roadmap=self.roadmap, course=None, course_title_override='Compilers',
            planned_hours=10.0, link='https://example.com/compilers', position=1)

    def link_course(self, **kwargs):
        course = Course.objects.create(owner=self.user, **kwargs)
        self.tracked.course = course
        self.tracked.save()
        return course

    def test_unlinked_steps_report_no_progress(self):
        self.assertEqual(self.roadmap.progress(), 0)
        self.assertEqual(self.roadmap.completed_count(), 0)
        self.assertEqual(self.roadmap.tracked_count(), 0)

    def test_roadmap_progress_follows_linked_course(self):
        self.link_course(title='Operating Systems', total_hours=20.0, hours_done=10.0)
        self.assertEqual(self.tracked.progress(), 50)
        self.assertEqual(self.roadmap.progress(), 25)
        self.assertEqual(self.roadmap.hours_spent(), 10.0)
        self.assertEqual(self.roadmap.tracked_count(), 1)

    def test_every_course_counts_once(self):
        self.link_course(title='Operating Systems', total_hours=20.0, hours_done=20.0)
        self.plain.progress_percent = 100
        self.plain.save()
        self.assertEqual(self.roadmap.completed_count(), 2)
        self.assertEqual(self.roadmap.progress(), 100)

    def test_mark_step_done_by_hand(self):
        response = self.client.post(
            reverse('roadmap_step_progress', kwargs={'slug': self.roadmap.slug, 'step_id': self.plain.id}),
        )
        self.assertRedirects(response, reverse('roadmap_detail', kwargs={'slug': self.roadmap.slug}))
        self.plain.refresh_from_db()
        self.assertEqual(self.plain.progress_percent, 100)
        self.assertTrue(self.plain.is_complete())

    def test_unmark_step_done(self):
        self.plain.progress_percent = 100
        self.plain.save()
        self.client.post(reverse('roadmap_step_progress', kwargs={'slug': self.roadmap.slug, 'step_id': self.plain.id}))
        self.plain.refresh_from_db()
        self.assertEqual(self.plain.progress_percent, 0)

    def test_mark_done_rejected_for_tracked_step(self):
        self.link_course(title='Operating Systems', total_hours=20.0)
        response = self.client.post(
            reverse('roadmap_step_progress', kwargs={'slug': self.roadmap.slug, 'step_id': self.tracked.id}),
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 400)
        self.tracked.refresh_from_db()
        self.assertEqual(self.tracked.progress_percent, 0)

    def test_step_progress_ajax(self):
        response = self.client.post(
            reverse('roadmap_step_progress', kwargs={'slug': self.roadmap.slug, 'step_id': self.plain.id}),
            {'progress_percent': '40'},
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['progress'], 40)

    def test_fork_step_creates_own_course_and_keeps_the_step(self):
        response = self.client.post(
            reverse('roadmap_fork_step', kwargs={'slug': self.roadmap.slug, 'step_id': self.tracked.id}),
        )
        course = Course.objects.get(title='Operating Systems')
        self.assertRedirects(response, reverse('course_detail', kwargs={'slug': course.slug}))
        self.assertEqual(course.owner, self.user)
        self.assertEqual(course.total_hours, 20.0)
        self.assertEqual(course.link, 'https://example.com/ostep')
        self.assertEqual(course.hours_done, 0)
        self.assertFalse(course.is_public)
        self.tracked.refresh_from_db()
        self.assertEqual(self.tracked.course, course)
        self.assertEqual(self.roadmap.steps.count(), 2)

    def test_forked_course_progress_shows_on_the_roadmap(self):
        self.client.post(reverse('roadmap_fork_step', kwargs={'slug': self.roadmap.slug, 'step_id': self.tracked.id}))
        course = Course.objects.get(title='Operating Systems')
        course.hours_done = 20.0
        course.save()
        response = self.client.get(reverse('roadmap_detail', kwargs={'slug': self.roadmap.slug}))
        self.assertEqual(response.context['progress'], 50)
        self.assertEqual(response.context['done_count'], 1)
        self.assertEqual(response.context['tracked_count'], 1)
        self.assertContains(response, '50%')

    def test_fork_step_twice_opens_the_same_course(self):
        url = reverse('roadmap_fork_step', kwargs={'slug': self.roadmap.slug, 'step_id': self.tracked.id})
        self.client.post(url)
        course = Course.objects.get(title='Operating Systems')
        response = self.client.post(url)
        self.assertRedirects(response, reverse('course_detail', kwargs={'slug': course.slug}))
        self.assertEqual(Course.objects.filter(owner=self.user).count(), 1)

    def test_fork_step_records_provenance_of_a_shared_course(self):
        shared = Course.objects.create(
            owner=self.other, title='Compilers', total_hours=30.0,
            link='https://example.com/shared', is_public=True)
        step = RoadmapCourse.objects.create(
            roadmap=self.roadmap, course=shared, course_title_override='Compilers',
            planned_hours=30.0, position=2)
        self.client.post(reverse('roadmap_fork_step', kwargs={'slug': self.roadmap.slug, 'step_id': step.id}))
        forked = Course.objects.get(owner=self.user)
        self.assertEqual(forked.forked_from, shared)
        self.assertEqual(forked.hours_done, 0)
        step.refresh_from_db()
        self.assertEqual(step.course, forked)

    def test_fork_step_requires_owner_of_the_roadmap(self):
        stranger = Roadmap.objects.create(owner=self.other, title='Not Yours')
        step = RoadmapCourse.objects.create(roadmap=stranger, course_title_override='Locked', position=0)
        response = self.client.post(
            reverse('roadmap_fork_step', kwargs={'slug': stranger.slug, 'step_id': step.id}),
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(Course.objects.filter(owner=self.user).exists())

    def test_fork_get_redirects_back_to_the_roadmap(self):
        response = self.client.get(
            reverse('roadmap_fork_step', kwargs={'slug': self.roadmap.slug, 'step_id': self.tracked.id}),
        )
        self.assertRedirects(response, reverse('roadmap_detail', kwargs={'slug': self.roadmap.slug}))

    def test_desk_lists_roadmaps_with_course_progress(self):
        self.link_course(title='Operating Systems', total_hours=20.0, hours_done=10.0)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Systems Path')
        self.assertContains(response, '0/2 courses done · 10h')
        self.assertContains(response, '25%')

    def test_roadmap_list_shows_progress(self):
        self.plain.progress_percent = 100
        self.plain.save()
        response = self.client.get(reverse('roadmaps'))
        self.assertContains(response, '1/2 courses')
        self.assertEqual(response.context['roadmaps'][0]['progress'], 50)

    def test_public_roadmap_hides_private_course_progress(self):
        self.link_course(title='Operating Systems', total_hours=20.0, hours_done=10.0, is_public=False)
        response = self.client.get(reverse('public:roadmap_public', kwargs={'slug': self.roadmap.slug}))
        step = response.context['steps'][0]
        self.assertFalse(step.is_trackable())
        self.assertEqual(step.course_progress(), 0)

    def test_public_roadmap_shows_public_course_progress(self):
        self.link_course(title='Operating Systems', total_hours=20.0, hours_done=10.0, is_public=True)
        response = self.client.get(reverse('public:roadmap_public', kwargs={'slug': self.roadmap.slug}))
        step = response.context['steps'][0]
        self.assertTrue(step.is_trackable())
        self.assertEqual(step.course_progress(), 50)
        self.assertEqual(response.context['progress'], 25)

    def test_course_page_lists_its_roadmaps(self):
        course = self.link_course(title='Operating Systems', total_hours=20.0)
        response = self.client.get(reverse('course_detail', kwargs={'slug': course.slug}))
        self.assertContains(response, 'Systems Path')
        self.assertContains(response, reverse('roadmap_detail', kwargs={'slug': self.roadmap.slug}))

    def test_studio_lists_per_course_progress(self):
        self.link_course(title='Operating Systems', total_hours=20.0, hours_done=10.0)
        response = self.client.get(reverse('roadmap_steps_edit', kwargs={'slug': self.roadmap.slug}))
        self.assertContains(response, 'Fork to my desk')
        self.assertContains(response, reverse('roadmap_fork_step', kwargs={'slug': self.roadmap.slug, 'step_id': self.plain.id}))
        self.assertEqual(response.context['progress'], 25)

    def test_clone_get_renders_the_shared_roadmap(self):
        response = self.client.get(reverse('roadmap_clone', kwargs={'slug': self.roadmap.slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Operating Systems')


class AddToDeskTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='password123')
        self.other = User.objects.create_user(username='owner', password='password123')
        self.client = Client()
        self.client.login(username='tester', password='password123')

    def test_create_from_shared_course_prefills_form(self):
        source = Course.objects.create(
            owner=self.other, title='Mathematics Bootcamp', total_hours=24.0,
            link='https://example.com/math', notes='Weekly drills',
            start_date='2026-01-05', is_public=True,
        )
        response = self.client.get(reverse('course_create'), {'from': source.slug})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Prefilled from owner\'s shared course')
        form = response.context['form']
        self.assertEqual(form['title'].value(), 'Mathematics Bootcamp')
        self.assertEqual(form['link'].value(), 'https://example.com/math')
        self.assertEqual(form['notes'].value(), 'Weekly drills')
        self.assertEqual(float(form['total_hours'].value()), 24.0)

    def test_create_from_own_public_course_prefills(self):
        source = Course.objects.create(
            owner=self.user, title='My Algorithm Course', total_hours=8.0, is_public=True,
        )
        response = self.client.get(reverse('course_create'), {'from': source.slug})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form']['title'].value(), 'My Algorithm Course')

    def test_create_from_private_course_ignored(self):
        source = Course.objects.create(
            owner=self.other, title='Secret Course', total_hours=8.0, is_public=False,
        )
        response = self.client.get(reverse('course_create'), {'from': source.slug})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Prefilled from')
        self.assertIsNone(response.context['form']['title'].value())

    def test_submit_prefill_creates_own_course(self):
        source = Course.objects.create(
            owner=self.other, title='Python Path', total_hours=18.0,
            notes='Build 5 projects', is_public=True,
        )
        response = self.client.post(reverse('course_create'), {
            'title': source.title,
            'link': source.link,
            'notes': source.notes,
            'start_date': '2026-01-05',
            'total_hours': str(source.total_hours),
            'is_public': 'on',
        })
        created = Course.objects.get(owner=self.user, title='Python Path')
        self.assertRedirects(response, reverse('course_detail', kwargs={'slug': created.slug}))
        self.assertEqual(created.total_hours, 18.0)
        self.assertEqual(created.notes, 'Build 5 projects')

    def test_public_page_links_prefill(self):
        source = Course.objects.create(
            owner=self.other, title='Calculus', total_hours=15.0, is_public=True,
        )
        response = self.client.get(reverse('public:course_public', kwargs={'slug': source.slug}))
        self.assertContains(
            response,
            f'href="{reverse("course_create")}?from={source.slug}"',
        )