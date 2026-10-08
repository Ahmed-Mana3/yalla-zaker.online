"""Views for the exclusive control panel.

The panel is reachable by URL for anyone: ``/exclusive-admin/``. Every write
goes through POST + CSRF, and an optional passphrase can be required by setting
``EXCLUSIVE_ADMIN_KEY`` in the environment (see ``settings.py``).
"""

from functools import wraps
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import ProtectedError, RestrictedError
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache

from .forms import form_for
from .registry import GROUP_BLURBS, get_spec, request_counts, totals

PAGE_SIZE = 25
SESSION_KEY = 'controlpanel_unlocked'
UNLOCK_URL = 'controlpanel:unlock'

# Both are raised by on_delete guards; Django 4.0 split PROTECT and RESTRICT
# into two sibling exceptions, and neither subclasses the other.
DELETE_BLOCKERS = (ProtectedError, RestrictedError)


def _required_key():
    return (getattr(settings, 'EXCLUSIVE_ADMIN_KEY', '') or '').strip()


def panel_open(request):
    """True when no passphrase is configured, or this session already has it."""
    if not _required_key():
        return True
    return request.session.get(SESSION_KEY, '') == _required_key()


def _safe_redirect_target(request, candidate, fallback):
    """Only follow a path on this host — never an absolute or protocol-relative URL."""
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return fallback


def require_open(view):
    """Allow the request through, or bounce to the passphrase screen."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not panel_open(request):
            nxt = request.get_full_path()
            return redirect(f'{reverse(UNLOCK_URL)}?{urlencode({"next": nxt})}')
        return view(request, *args, **kwargs)

    return wrapper


# ------------------------------------------------------------------ list state

def _list_params(request, spec):
    """The query string that keeps the current table view alive across a write.

    Search, page, and the toggled boolean all survive an edit, delete, duplicate
    or quick toggle, so the panel never dumps you back at page 1 with no filter.
    """
    params = {}
    term = (request.GET.get('q') or request.POST.get('q') or '').strip()
    if term:
        params['q'] = term
    page = request.GET.get('page') or request.POST.get('page')
    if page and page.isdigit():
        params['page'] = page
    return params


def _paginate(request, spec, queryset):
    paginator = Paginator(queryset, PAGE_SIZE)
    page = paginator.get_page(request.GET.get('page'))
    return {
        'page': page,
        'paginator': paginator,
        'rows': [
            {
                'obj': obj,
                'pk': obj.pk,
                'label': str(obj),
                'cells': spec.row_cells(obj),
            }
            for obj in page.object_list
        ],
        'total': paginator.count,
        'is_filtered': bool(request.GET.get('q')),
    }


def _back_to(spec, request=None, **kwargs):
    """Return to the records table, keeping the caller's search and page."""
    query = {}
    if request is not None:
        query = _list_params(request, spec)
    query.update(kwargs)
    url = reverse('controlpanel:records', args=[spec.key])
    return redirect(f'{url}?{urlencode(query)}' if query else url)


def _back_to_edit(spec, pk, request=None):
    return redirect(reverse('controlpanel:record_edit', args=[spec.key, pk]))


# ------------------------------------------------------------------ unlock

@never_cache
def unlock(request):
    """Optional passphrase gate — only shown when EXCLUSIVE_ADMIN_KEY is set."""
    required = _required_key()
    if not required:
        return redirect('controlpanel:dashboard')

    error = ''
    next_url = request.GET.get('next') or request.POST.get('next') or ''
    if request.method == 'POST':
        if request.POST.get('key', '').strip() == required:
            request.session[SESSION_KEY] = required
            request.session.modified = True
            return redirect(_safe_redirect_target(
                request, next_url, reverse('controlpanel:dashboard')
            ))
        error = 'That passphrase does not match.'

    return render(request, 'controlpanel/unlock.html', {
        'error': error,
        'next': next_url,
    }, status=401 if error else 200)


def require_post(view):
    """405 anything that is not a POST, before the passphrase gate runs."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.method != 'POST':
            return HttpResponseNotAllowed(['POST'])
        return view(request, *args, **kwargs)

    return wrapper


@require_post
@require_open
def lock(request):
    """Drop the session passphrase so the next visit asks again."""
    request.session.pop(SESSION_KEY, None)
    request.session.modified = True
    messages.info(request, 'Panel locked again.')
    return redirect(reverse(UNLOCK_URL))


# ------------------------------------------------------------------ dashboard

@never_cache
@require_open
def dashboard(request):
    counts = request_counts(request)
    return render(request, 'controlpanel/dashboard.html', {
        'rows': totals(counts),
        'by_key': counts,
        'total_records': sum(counts.values()),
        'group_blurbs': GROUP_BLURBS,
    })


# ------------------------------------------------------------------ records

@never_cache
@require_open
def records(request, model_key):
    spec = get_spec(model_key)
    term = request.GET.get('q', '')
    queryset = spec.search_queryset(spec.get_queryset(), term)

    context = {
        'spec': spec,
        'term': term,
        'list_params': _list_params(request, spec),
        'toggle_fields': spec.toggle_fields,
    }
    context.update(_paginate(request, spec, queryset))
    return render(request, 'controlpanel/records.html', context)


# ------------------------------------------------------------------ add / edit

@never_cache
@require_open
def record_add(request, model_key):
    spec = get_spec(model_key)
    form = form_for(spec, data=request.POST or None)

    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'{spec.singular} “{obj}” added.')
        return _back_to(spec, request)

    return render(request, 'controlpanel/form.html', {
        'spec': spec,
        'form': form,
        'mode': 'add',
        'heading': f'Add {spec.singular_lower}',
        'list_params': _list_params(request, spec),
    })


@never_cache
@require_open
def record_edit(request, model_key, pk):
    spec = get_spec(model_key)
    obj = get_object_or_404(spec.model, pk=pk)
    form = form_for(spec, data=request.POST or None, instance=obj)

    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'{spec.singular} “{obj}” updated.')
        return _back_to(spec, request)

    return render(request, 'controlpanel/form.html', {
        'spec': spec,
        'form': form,
        'obj': obj,
        'mode': 'edit',
        'heading': f'Edit {spec.singular_lower}',
        'list_params': _list_params(request, spec),
    })


# ------------------------------------------------------------------ delete

@never_cache
@require_open
def record_delete(request, model_key, pk):
    spec = get_spec(model_key)
    obj = get_object_or_404(spec.model, pk=pk)

    if request.method == 'POST':
        label = str(obj)
        try:
            obj.delete()
        except DELETE_BLOCKERS as exc:
            messages.error(request, f'“{label}” is still referenced and cannot be deleted. {_blocker_hint(exc)}')
        else:
            messages.success(request, f'{spec.singular} “{label}” deleted.')
        return _back_to(spec, request)

    return render(request, 'controlpanel/confirm_delete.html', {
        'spec': spec,
        'obj': obj,
        'label': str(obj),
        'cascade': spec.cascade_targets(obj),
        'list_params': _list_params(request, spec),
    })


def _blocker_hint(exc):
    """Name the records that stopped the delete, when Django reports them."""
    blocked = getattr(exc, 'protected_objects', None) or ()
    if not blocked:
        return ''
    labels = sorted({str(o) for o in blocked})
    return 'Still referenced: ' + ', '.join(labels[:5]) + ('…' if len(labels) > 5 else '.')


@require_post
@require_open
def bulk_delete(request, model_key):
    """Two steps: POST the selection to preview, POST again with ``confirmed``."""
    spec = get_spec(model_key)
    queryset = spec.model._default_manager.filter(pk__in=request.POST.getlist('pks'))
    objects = list(queryset)
    count = len(objects)

    if not count:
        messages.warning(request, 'Nothing selected, so nothing was deleted.')
        return _back_to(spec, request)

    if request.POST.get('confirmed'):
        label = spec.plural_for(count)
        try:
            spec.model._default_manager.filter(pk__in=[o.pk for o in objects]).delete()
        except DELETE_BLOCKERS as exc:
            messages.error(request, f'Some of those {spec.title.lower()} are still referenced. {_blocker_hint(exc)}')
        else:
            messages.success(request, f'{label} deleted.')
        return _back_to(spec, request)

    return render(request, 'controlpanel/confirm_delete.html', {
        'spec': spec,
        'obj': None,
        'bulk': True,
        'count': count,
        'count_label': spec.plural_for(count),
        'objects': objects,
        'label': spec.plural_for(count),
        'cascade': spec.bulk_cascade_targets(objects),
        'list_params': _list_params(request, spec),
    })


@require_post
@require_open
def duplicate(request, model_key, pk):
    """Copy a record as a starting point for a new one."""
    spec = get_spec(model_key)
    obj = get_object_or_404(spec.model, pk=pk)

    if not spec.can_duplicate:
        blocked = ', '.join(spec.blocked_unique_fields)
        messages.warning(
            request,
            f'A {spec.singular_lower} cannot be copied — {blocked} must be unique, '
            f'so add a new one instead.',
        )
        return redirect(reverse('controlpanel:record_add', args=[spec.key]))

    clone = spec.model()
    for name in spec.copyable_fields():
        field = spec.model._meta.get_field(name)
        setattr(clone, field.attname, getattr(obj, field.attname))
    # A duplicate must not collide with a unique slug.
    if hasattr(clone, 'slug'):
        clone.slug = ''
    clone.pk = None
    try:
        clone.save()
    except DELETE_BLOCKERS as exc:
        messages.error(request, f'That {spec.singular_lower} could not be copied. {_blocker_hint(exc)}')
        return _back_to(spec, request)
    messages.success(request, f'Copied to a new {spec.singular_lower}. Give it a name, then save.')
    return _back_to_edit(spec, clone.pk)


@require_post
@require_open
def toggle_flag(request, model_key, pk, field_name):
    """Flip a boolean from the table without opening the full form."""
    spec = get_spec(model_key)
    if field_name not in spec.form_fields:
        raise Http404

    obj = get_object_or_404(spec.model, pk=pk)
    model_field = spec.model._meta.get_field(field_name)
    if model_field.get_internal_type() != 'BooleanField':
        raise Http404

    setattr(obj, field_name, not getattr(obj, field_name))
    obj.save(update_fields=[field_name])
    label = model_field.verbose_name
    state = 'on' if getattr(obj, field_name) else 'off'
    messages.info(request, f'{obj}: {label} is now {state}.')
    return redirect(_safe_redirect_target(
        request,
        request.POST.get('next') or request.META.get('HTTP_REFERER'),
        reverse('controlpanel:records', args=[spec.key]),
    ))
