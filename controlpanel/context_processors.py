"""Template context shared by every control panel page.

Builds the sidebar navigation (grouped record types) and their live row counts
once per request, so no view has to remember to pass them.
"""

from .registry import GROUP_BLURBS, GROUPS, REGISTRY


def panel(request):
    if not request.resolver_match.namespace == 'controlpanel':
        return {}

    nav = []
    for group in GROUPS:
        specs = []
        for spec in REGISTRY:
            if spec.group != group:
                continue
            specs.append({
                'spec': spec,
                'count': spec.model._default_manager.count(),
            })
        nav.append({
            'name': group,
            'blurb': GROUP_BLURBS.get(group, ''),
            'specs': specs,
        })

    locked = bool(request.session.get('controlpanel_unlocked'))
    return {
        'cp_nav': nav,
        'cp_locked': locked,
    }