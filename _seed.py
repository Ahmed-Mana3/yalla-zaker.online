"""Seed the REAL dev sqlite DB with demo data for live browser auditing."""
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yalla_zaker.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import django  # noqa: E402

django.setup()

from datetime import timedelta  # noqa: E402

from django.contrib.auth.models import User  # noqa: E402
from django.utils import timezone  # noqa: E402

from accounts.models import Friendship, Profile  # noqa: E402
from challenges.models import Challenge, ChallengeMember  # noqa: E402
from courses.models import Course, Roadmap, RoadmapCourse  # noqa: E402
from studysessions.models import StudySegment, StudySession  # noqa: E402

now = timezone.now()
PWD = 'Str0ngPass!234'

if User.objects.filter(username='alice').exists():
    print('already seeded')
    sys.exit(0)

me = User.objects.create_user('alice', 'alice@example.com', PWD, first_name='Alice')
bob = User.objects.create_user('bob', 'bob@example.com', PWD)
carol = User.objects.create_user('carol', 'carol@example.com', PWD)
dave = User.objects.create_user('dave', 'dave@example.com', PWD)
for u in (me, bob, carol, dave):
    Profile.objects.get_or_create(user=u)

c1 = Course.objects.create(owner=me, title='Advanced Electrodynamics',
                            notes='Syllabus, weekly plan, problem sets 1-9.',
                            start_date=now.date() - timedelta(days=20), total_hours=60,
                            hours_done=12.5, is_public=True)
c2 = Course.objects.create(owner=me, title='Organic Chemistry II With A Very Long Title Here',
                            notes='Reagents memorised weekly.',
                            start_date=now.date() - timedelta(days=5), total_hours=40,
                            hours_done=2, is_public=False)
c3 = Course.objects.create(owner=bob, title='Bob Public Course', start_date=now.date(),
                           total_hours=10, is_public=True)
c1.end_date = now.date() - timedelta(days=1)
c1.save()

rm = Roadmap.objects.create(owner=me, title='Full Physics Track For The Semester',
                            description='Everything needed for the final.', is_public=True)
RoadmapCourse.objects.create(roadmap=rm, course=c1, position=0, planned_hours=60)
RoadmapCourse.objects.create(roadmap=rm, course=None, position=1,
                             course_title_override='Linear Algebra Review',
                             planned_hours=10, link='https://example.com/lin-alg')
rmr = Roadmap.objects.create(owner=bob, title='Bob Roadmap', is_public=True)
RoadmapCourse.objects.create(roadmap=rmr, course=c3, position=0, planned_hours=10)

ch = Challenge.objects.create(title='Study Marathon', starts_at=now.date() - timedelta(days=1),
                              ends_at=now.date() + timedelta(days=9), created_by=me)
ChallengeMember.objects.create(challenge=ch, user=me)
ChallengeMember.objects.create(challenge=ch, user=bob)

Friendship.objects.create(from_user=me, to_user=bob)
Friendship.objects.create(from_user=bob, to_user=me)
Friendship.objects.create(from_user=carol, to_user=me)
Friendship.objects.create(from_user=dave, to_user=me)

s1 = StudySession.objects.create(user=me, course=c1, started_at=now - timedelta(hours=3),
                                 ended_at=now - timedelta(hours=1), duration_seconds=7200,
                                 status='finished', checked_in=True, manual_seconds=7200)
StudySegment.objects.create(session=s1, started_at=now - timedelta(hours=3),
                            ended_at=now - timedelta(hours=1))
s2 = StudySession.objects.create(user=me, course=c2, started_at=now - timedelta(minutes=42),
                                 status='active')
StudySegment.objects.create(session=s2, started_at=now - timedelta(minutes=42))
s3 = StudySession.objects.create(user=bob, course=c3, started_at=now - timedelta(minutes=5),
                                 status='active')
StudySegment.objects.create(session=s3, started_at=now - timedelta(minutes=5))

print('seeded alice/bob/carol/dave with', PWD)