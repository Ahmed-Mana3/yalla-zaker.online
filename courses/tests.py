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