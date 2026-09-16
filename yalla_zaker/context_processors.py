from django.conf import settings


def seo(request):
    """Inject canonical URL helpers for SEO tags, sitemap and robots.txt.

    The host defaults to the request host so local development and any
    deployed domain just work; set SEO_CANONICAL_HOST to pin a real domain.
    """
    host = getattr(settings, 'SEO_CANONICAL_HOST', None) or request.get_host()
    scheme = 'https' if request.is_secure() else 'http'
    site = f'{scheme}://{host}'
    return {
        'canonical_site': site,
        'canonical_path': request.path,
    }