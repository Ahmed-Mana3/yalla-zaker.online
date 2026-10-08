"""Template context shared by every control panel page.

Builds the sidebar navigation (grouped record types) and their live row counts
once per request, so no view has to remember to pass them.
"""

from .registry import GROUP_BLURBS, GROUPS, REGISTRY, request_counts


def panel(request):
    match = getattr(request, 'resolver_match', None)
    if match is None or match.namespace != 'controlpanel':
        return {}

    by_key = request_counts(request)
    nav = []
    for group in GROUPS:
        specs = []
        for spec in REGISTRY:
            if spec.group != group:
                continue
            specs.append({'spec': spec, 'count': by_key.get(spec.key, 0)})
        nav.append({
            'name': group,
            'blurb': GROUP_BLURBS.get(group, ''),
            'specs': specs,
        })

    return {
        'cp_nav': nav,
        'cp_locked': bool(request.session.get('controlpanel_unlocked')),
    }
