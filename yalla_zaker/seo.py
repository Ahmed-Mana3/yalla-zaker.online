"""SEO endpoints: robots.txt, sitemap.xml and llms.txt.

These are plain views that reflect the current request host (or the pinned
SEO_CANONICAL_HOST), so they behave correctly in development and production.
"""
from django.contrib.auth import get_user_model
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone

from challenges.models import Challenge
from courses.models import Course, Roadmap


# ------------------------------------------------------------------ robots.txt


def robots_txt(request):
    return render(request, 'seo/robots.txt', {}, content_type='text/plain')


def sitemap_xml(request):
    from django.conf import settings

    host = getattr(settings, 'SEO_CANONICAL_HOST', None) or request.get_host()
    scheme = 'https' if request.is_secure() else 'http'
    site = f'{scheme}://{host}'

    def loc(name, *args, **kwargs):
        return site + reverse(name, args=args, kwargs=kwargs)

    today = timezone.now().date()
    entries = [
        {'loc': loc('home'), 'changefreq': 'daily', 'priority': '1.0', 'lastmod': None},
        {'loc': loc('signup'), 'changefreq': 'monthly', 'priority': '0.8', 'lastmod': None},
        {'loc': loc('login'), 'changefreq': 'monthly', 'priority': '0.5', 'lastmod': None},
        {'loc': loc('challenges'), 'changefreq': 'daily', 'priority': '0.6', 'lastmod': None},
    ]

    # Public, share-by-link course pages.
    for course in Course.objects.filter(is_public=True).order_by('-updated_at'):
        entries.append({
            'loc': loc('public:course_public', slug=course.slug),
            'changefreq': 'weekly',
            'priority': '0.7',
            'lastmod': course.updated_at.date().isoformat(),
        })

    # Public, share-by-link roadmap pages.
    for roadmap in Roadmap.objects.filter(is_public=True).order_by('-updated_at'):
        entries.append({
            'loc': loc('public:roadmap_public', slug=roadmap.slug),
            'changefreq': 'weekly',
            'priority': '0.6',
            'lastmod': roadmap.updated_at.date().isoformat(),
        })

    # Public challenge boards.
    for challenge in Challenge.objects.order_by('-created_at'):
        entries.append({
            'loc': loc('challenge_detail', pk=challenge.pk),
            'changefreq': 'daily',
            'priority': '0.6',
            'lastmod': None,
        })

    # Public user profiles.
    for user in get_user_model().objects.order_by('-date_joined'):
        entries.append({
            'loc': loc('profile', username=user.username),
            'changefreq': 'weekly',
            'priority': '0.4',
            'lastmod': None,
        })

    return render(request, 'seo/sitemap.xml', {
        'entries': entries,
        'lastmod': today.isoformat(),
    }, content_type='application/xml')


# ------------------------------------------------------------------- llms.txt


def llms_txt(request):
    return render(request, 'seo/llms.txt', {}, content_type='text/plain; charset=utf-8')