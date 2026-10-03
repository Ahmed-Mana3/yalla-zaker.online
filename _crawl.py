"""Throwaway crawler: seeds data, logs in, walks every link/form, reports breakage."""
import os
import re
import sys
from collections import defaultdict
from urllib.parse import urljoin, urlparse, urldefrag

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yalla_zaker.test_settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import django  # noqa: E402

django.setup()

from datetime import timedelta  # noqa: E402

from django.contrib.auth.models import User  # noqa: E402
from django.test import Client  # noqa: E402
from django.test.utils import setup_test_environment, teardown_test_environment  # noqa: E402
from django.test.runner import DiscoverRunner  # noqa: E402
from django.utils import timezone  # noqa: E402

setup_test_environment()
runner = DiscoverRunner(verbosity=0, interactive=False)
old_config = runner.setup_databases()

from accounts.models import Friendship, Profile  # noqa: E402
from challenges.models import Challenge, ChallengeMember  # noqa: E402
from courses.models import Course, Roadmap, RoadmapCourse  # noqa: E402
from studysessions.models import StudySegment, StudySession  # noqa: E402

now = timezone.now()

me = User.objects.create_user('alice', 'alice@example.com', 'Str0ngPass!234')
bob = User.objects.create_user('bob', 'bob@example.com', 'Str0ngPass!234')
carol = User.objects.create_user('carol', 'carol@example.com', 'Str0ngPass!234')
Profile.objects.get_or_create(user=me)
Profile.objects.get_or_create(user=bob)
Profile.objects.get_or_create(user=carol)

c1 = Course.objects.create(owner=me, title='Advanced Electrodynamics',
                            notes='Syllabus, weekly plan.',
                            start_date=now.date() - timedelta(days=10),
                            total_hours=60, hours_done=12.5, is_public=True)
c2 = Course.objects.create(owner=me, title='Organic Chemistry II',
                            start_date=now.date() - timedelta(days=3),
                            total_hours=40, hours_done=2, is_public=False)
c3 = Course.objects.create(owner=bob, title='Bob Public Course', start_date=now.date(),
                           total_hours=10, is_public=True)
c1.end_date = now.date() - timedelta(days=1)
c1.save()

rm = Roadmap.objects.create(owner=me, title='Full Physics Track', description='Everything for the semester.',
                            is_public=True)
RoadmapCourse.objects.create(roadmap=rm, course=c1, position=0, planned_hours=60)
RoadmapCourse.objects.create(roadmap=rm, course=None, position=1,
                             course_title_override='Step Two', planned_hours=10,
                             link='https://example.com/x')
rmr = Roadmap.objects.create(owner=bob, title='Bob Roadmap', is_public=True)
RoadmapCourse.objects.create(roadmap=rmr, course=c3, position=0, planned_hours=10)

ch = Challenge.objects.create(title='Study Marathon', starts_at=now.date() - timedelta(days=1),
                              ends_at=now.date() + timedelta(days=9), created_by=me)
ChallengeMember.objects.create(challenge=ch, user=me)
ChallengeMember.objects.create(challenge=ch, user=bob)

Friendship.objects.create(from_user=me, to_user=bob)
Friendship.objects.create(from_user=bob, to_user=me)
Friendship.objects.create(from_user=carol, to_user=me)

s1 = StudySession.objects.create(user=me, course=c1, started_at=now - timedelta(hours=3),
                                 ended_at=now - timedelta(hours=1), duration_seconds=7200,
                                 status='finished', checked_in=True, manual_seconds=7200)
StudySegment.objects.create(session=s1, started_at=now - timedelta(hours=3), ended_at=now - timedelta(hours=1))

s2 = StudySession.objects.create(user=me, course=c2, started_at=now - timedelta(minutes=30), status='active')
StudySegment.objects.create(session=s2, started_at=now - timedelta(minutes=30))

s3 = StudySession.objects.create(user=bob, course=c3, started_at=now - timedelta(minutes=5), status='active')
StudySegment.objects.create(session=s3, started_at=now - timedelta(minutes=5))

HREF_RE = re.compile(r'<a\b[^>]*?href=["\']([^"\']+)["\']', re.I | re.S)
FORM_RE = re.compile(r'<form\b[^>]*?action=["\']([^"\']*)["\'][^>]*>(.*?)</form>', re.I | re.S)

problems = []
visited = {}
form_problems = []


def note(kind, url, detail):
    problems.append((kind, url, detail))


def crawl(client, seed, label):
    queue = [seed]
    seen = set()
    while queue:
        path = queue.pop(0)
        path, _ = urldefrag(path)
        if path in seen:
            continue
        seen.add(path)
        if not path.startswith('/'):
            continue
        try:
            r = client.get(path, follow=False)
        except Exception as exc:  # noqa: BLE001
            note('EXC', path, f'{type(exc).__name__}: {exc}')
            continue
        status = r.status_code
        visited[(label, path)] = status
        if status in (301, 302):
            loc = r.headers.get('Location', '')
            if path != loc and loc.startswith('/'):
                queue.append(loc)
            continue
        if status >= 400:
            note(f'HTTP{status}', path, (r.content[:200].decode('utf-8', 'replace') if 'text/html' in r.headers.get('Content-Type', '') else ''))
            continue
        if 'text/html' not in r.headers.get('Content-Type', ''):
            continue
        html = r.content.decode('utf-8', 'replace')

        # link targets
        for href in HREF_RE.findall(html):
            if href.startswith(('mailto:', 'tel:', 'javascript:', '#')):
                continue
            target = urlparse(urljoin(path, href)).path
            if target.startswith('/static/'):
                sr = client.get(target)
                if sr.status_code != 200:
                    note(f'STATIC{sr.status_code}', target, 'missing static asset')
                continue
            if target.startswith('/admin'):
                continue
            queue.append(target)

        # forms
        for action, inner in FORM_RE.findall(html):
            a = urlparse(urljoin(path, action)).path
            method = 'get'
            mt = re.search(r'method=["\']?(\w+)', action + ' ' + '', re.I)
            mt2 = re.search(r'method=["\'](post|get)["\']', inner, re.I)
            if mt2:
                method = mt2.group(1).lower()
            fields = re.findall(r'<(input|textarea|select)\b[^>]*name=["\']([^"\']+)["\']', inner, re.I)
            csrf = re.search(r'name=["\']csrfmiddlewaretoken["\']\s+value=["\']([^"\']+)["\']', inner, re.I)
            data = {}
            for tag, name in fields:
                if tag.lower() == 'textarea':
                    data[name] = 'x'
                elif 'password' in re.search(rf'name=["\']{re.escape(name)}["\'][^>]*', inner, re.I).group(0).lower():
                    data[name] = 'Str0ngPass!234'
                else:
                    data[name] = '1'
            if csrf:
                data['csrfmiddlewaretoken'] = csrf.group(1)
            if method == 'get':
                url = a + ('?' + '&'.join(f'{k}={v}' for k, v in data.items()) if data else '')
                try:
                    rr = client.get(url, follow=False)
                except Exception as exc:  # noqa: BLE001
                    note('FORM_EXC', url, f'{type(exc).__name__}: {exc}')
                    continue
                if rr.status_code >= 500:
                    form_problems.append(('GET', url, rr.status_code))
                    note(f'FORM{rr.status_code}', url, '')
            else:
                try:
                    rr = client.post(a, data, follow=False)
                except Exception as exc:  # noqa: BLE001
                    note('FORM_EXC', a, f'{type(exc).__name__}: {exc}')
                    continue
                if rr.status_code >= 400:
                    # 400 from csrf/validation may be legit; record
                    form_problems.append(('POST', a, rr.status_code, sorted(data.keys())))
                    if rr.status_code >= 500:
                        note(f'FORM{rr.status_code}', a, '')


# anonymous
anon = Client()
crawl(anon, '/', 'anon')
crawl(anon, '/login/', 'anon')
crawl(anon, '/signup/', 'anon')
crawl(anon, '/courses/', 'anon')

# authenticated
auth = Client()
assert auth.login(username='alice', password='Str0ngPass!234'), 'login failed'
crawl(auth, '/dashboard/', 'auth')

# other user profile as bob
bobc = Client()
bobc.login(username='bob', password='Str0ngPass!234')
crawl(bobc, '/users/alice/', 'bob')

# no-auth client hitting private pages
crawl(Client(), '/dashboard/', 'noauth')
crawl(Client(), '/courses/add/', 'noauth')
crawl(Client(), '/friends/', 'noauth')
crawl(Client(), '/challenges/', 'noauth')

runner.teardown_databases(old_config)
teardown_test_environment()

print('=' * 70)
print('STATUS SUMMARY (unique paths):')
bys = defaultdict(set)
for (lab, p), s in visited.items():
    bys[s].add(p)
for s in sorted(bys):
    print(f'  {s}: {len(bys[s])}')
print()
print(f'PROBLEMS: {len(problems)}')
for kind, url, detail in problems:
    print(f'  [{kind}] {url}')
    if detail:
        print(f'        {detail[:160]}')
print()
print(f'FORM NON-2xx: {len(form_problems)}')
for fp in form_problems:
    print(f'  {fp}')