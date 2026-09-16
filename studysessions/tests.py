from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from courses.models import Course
from studysessions.models import StudySession

User = get_user_model()


class StudySessionFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tester', password='password123')
        self.client = Client()
        self.client.login(username='tester', password='password123')
        self.course = Course.objects.create(
            owner=self.user,
            title='Python Deep Dive',
            total_hours=10.0,
            hours_done=2.0
        )

    def test_study_index_setup_mode(self):
        """When no session is active, study page displays setup mode."""
        response = self.client.get(reverse('study'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Prepare Your Study Session')
        self.assertContains(response, 'Choose Duration')
        self.assertContains(response, 'Python Deep Dive')
        self.assertContains(response, 'Light the Lamp')

    def test_session_start_with_target_and_course(self):
        """Starting a session creates an active StudySession."""
        response = self.client.post(reverse('session_start'), {
            'course': self.course.id,
            'target': '45',
        })
        self.assertRedirects(response, reverse('study'))
        session = StudySession.current_for(self.user)
        self.assertIsNotNone(session)
        self.assertEqual(session.status, StudySession.STATUS_ACTIVE)
        self.assertEqual(session.target_minutes, 45)
        self.assertEqual(session.course, self.course)

    def test_session_pause_and_resume(self):
        """Session can be paused and resumed."""
        self.client.post(reverse('session_start'), {'course': self.course.id, 'target': '25'})
        session = StudySession.current_for(self.user)

        # Pause
        self.client.post(reverse('session_pause'))
        session.refresh_from_db()
        self.assertEqual(session.status, StudySession.STATUS_PAUSED)

        # Resume
        self.client.post(reverse('session_resume'))
        session.refresh_from_db()
        self.assertEqual(session.status, StudySession.STATUS_ACTIVE)

    def test_session_end_course_prompts_duration_checkin(self):
        """Ending a course session puts it in pending checkin mode asking for course duration hours."""
        self.client.post(reverse('session_start'), {'course': self.course.id, 'target': '45'})
        session = StudySession.current_for(self.user)
        session.duration_seconds = 3600  # 1 hr
        session.save()

        # End session
        self.client.post(reverse('session_end'))
        session.refresh_from_db()
        self.assertEqual(session.status, StudySession.STATUS_FINISHED)
        self.assertFalse(session.checked_in)

        # View study page - should render the course duration check-in
        response = self.client.get(reverse('study'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'How many minutes did you finish from the course?')
        self.assertContains(response, 'Python Deep Dive')
        self.assertContains(response, 'log-minutes')

    def test_session_log_minutes(self):
        """User submits minutes completed (e.g. 90 min = 1.5h)."""
        session = StudySession.objects.create(
            user=self.user,
            course=self.course,
            status=StudySession.STATUS_FINISHED,
            duration_seconds=3600,
            checked_in=False
        )

        response = self.client.post(reverse('session_log'), {
            'session_id': session.id,
            'minutes': '90',
        })
        self.assertRedirects(response, reverse('study'))

        session.refresh_from_db()
        self.assertTrue(session.checked_in)
        self.assertEqual(session.manual_seconds, 5400)
        self.assertEqual(session.manual_hours, 1.5)

        self.course.refresh_from_db()
        self.assertEqual(self.course.hours_done, 3.5)
        self.assertEqual(self.course.remaining_hours(), 6.5)

    def test_session_log_decimal_hours(self):
        """User can submit decimal hours completed (e.g. 1.5h)."""
        session = StudySession.objects.create(
            user=self.user,
            course=self.course,
            status=StudySession.STATUS_FINISHED,
            duration_seconds=3600,
            checked_in=False
        )

        response = self.client.post(reverse('session_log'), {
            'session_id': session.id,
            'hours': '1.5',
        })
        self.assertRedirects(response, reverse('study'))

        session.refresh_from_db()
        self.assertTrue(session.checked_in)
        self.assertEqual(session.manual_seconds, 5400)
        self.assertEqual(session.manual_hours, 1.5)

        self.course.refresh_from_db()
        self.assertEqual(self.course.hours_done, 3.5)
        self.assertEqual(self.course.remaining_hours(), 6.5)

    def test_session_log_hours_and_minutes(self):
        """User can submit hours and minutes combined."""
        session = StudySession.objects.create(
            user=self.user,
            course=self.course,
            status=StudySession.STATUS_FINISHED,
            duration_seconds=3600,
            checked_in=False
        )

        response = self.client.post(reverse('session_log'), {
            'session_id': session.id,
            'hours': '1',
            'minutes': '30',
        })
        self.assertRedirects(response, reverse('study'))

        session.refresh_from_db()
        self.assertTrue(session.checked_in)
        self.assertEqual(session.manual_seconds, 5400)

        self.course.refresh_from_db()
        self.assertEqual(self.course.hours_done, 3.5)

    def test_session_log_skip(self):
        """User can skip logging without crediting hours to the course."""
        session = StudySession.objects.create(
            user=self.user,
            course=self.course,
            status=StudySession.STATUS_FINISHED,
            duration_seconds=3600,
            checked_in=False
        )

        response = self.client.post(reverse('session_log'), {
            'session_id': session.id,
            'action': 'skip',
        })
        self.assertRedirects(response, reverse('study'))

        session.refresh_from_db()
        self.assertTrue(session.checked_in)
        self.assertEqual(session.manual_seconds, 0)

        self.course.refresh_from_db()
        self.assertEqual(self.course.hours_done, 2.0)

    def test_session_log_completes_course_when_goal_reached(self):
        """When course hours meet or exceed total_hours, course is automatically marked complete."""
        session = StudySession.objects.create(
            user=self.user,
            course=self.course,
            status=StudySession.STATUS_FINISHED,
            duration_seconds=7200,
            checked_in=False
        )

        # Course was at 2.0h / 10.0h; adding 8.0h finishes it
        response = self.client.post(reverse('session_log'), {
            'session_id': session.id,
            'hours': '8.0',
        })
        self.assertRedirects(response, reverse('study'))

        self.course.refresh_from_db()
        self.assertEqual(self.course.hours_done, 10.0)
        self.assertIsNotNone(self.course.end_date)
        self.assertFalse(self.course.is_active_course())

