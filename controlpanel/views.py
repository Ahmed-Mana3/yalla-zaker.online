"""Views for the exclusive control panel.

The panel is reachable by URL for anyone: ``/exclusive-admin/``. Every write
goes through POST + CSRF, and an optional passphrase can be required by setting
``EXCLUSIVE_ADMIN_KEY`` in the environment (see ``settings.py``).
"""

from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import ProtectedError
from django.http import Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from .forms import form_for
from .registry import GROUP_BLURBS, get_spec, totals

PAGE_SIZE = 25
SESSION_KEY = 'controlpanel_unlocked'
UNLOCK_URL = 'controlpanel:unlock'


def _required_key():
    return (getattr(settings, 'EXCLUSIVE_ADMIN_KEY', '') or '').strip()


def panel_open(request):
    """True when no passphrase is configured, or this session already has it."""
    if not _required_key():
        return True
    return request.session.get(SESSION_KEY, '') == _required_key()


def require_open(view):
    """Allow the request through, or bounce to the passphrase screen."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not panel_open(request):
            return redirect(f'{reverse(UNLOCK_URL)}?next={request.path}')
        return view(request, *args, **kwargs)

    return wrapper


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


def _back_to(spec, **kwargs):
    return redirect(reverse('controlpanel:records', args=[spec.key], kwargs=kwargs))


# ------------------------------------------------------------------ unlock

@never_cache
def unlock(request):
    """Optional passphrase gate — only shown when EXCLUSIVE_ADMIN_KEY is set."""
    required = _required_key()
    if not required:
        return redirect('controlpanel:dashboard')

    error = ''
    if request.method == 'POST':
        if request.POST.get('key', '').strip() == required:
            request.session[SESSION_KEY] = required
            request.session.modified = True
            nxt = request.GET.get('next') or request.POST.get('next') or ''
            return redirect(nxt if nxt.startswith('/') else reverse('controlpanel:dashboard'))
        error = 'That passphrase does not match.'
        messages.error(request, error)

    return render(request, 'controlpanel/unlock.html', {
        'error': error,
        'next': request.GET.get('next', ''),
    }, status=401 if error else 200)


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
    rows = totals()
    by_key = {row['spec'].key: row['count'] for row in rows}
    return render(request, 'controlpanel/dashboard.html', {
        'rows': rows,
        'by_key': by_key,
        'total_records': sum(by_key.values()),
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
        return _back_to(spec)

    return render(request, 'controlpanel/form.html', {
        'spec': spec,
        'form': form,
        'mode': 'add',
        'heading': f'Add {spec.singular_lower}',
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
        return _back_to(spec)

    return render(request, 'controlpanel/form.html', {
        'spec': spec,
        'form': form,
        'obj': obj,
        'mode': 'edit',
        'heading': f'Edit {spec.singular_lower}',
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
        except ProtectedError:
            messages.error(request, f'“{label}” is still referenced and cannot be deleted.')
        else:
            messages.success(request, f'{spec.singular} “{label}” deleted.')
        return _back_to(spec)

    return render(request, 'controlpanel/confirm_delete.html', {
        'spec': spec,
        'obj': obj,
        'label': str(obj),
        'cascade': spec.cascade_targets(obj),
    })


@require_open
def bulk_delete(request, model_key):
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    spec = get_spec(model_key)
    pks = request.POST.getlist('pks')
    queryset = spec.model._default_manager.filter(pk__in=pks)
    count = queryset.count()

    if not count:
        messages.warning(request, 'Nothing selected, so nothing was deleted.')
        return _back_to(spec)

    if request.POST.get('confirmed'):
        try:
            queryset.delete()
        except ProtectedError:
            messages.error(request, 'Some records are still referenced and were not deleted.')
        else:
            messages.success(request, f'{spec.plural_for(count)} deleted.')
        return _back_to(spec)

    return render(request, 'controlpanel/confirm_delete.html', {
        'spec': spec,
        'obj': None,
        'bulk': True,
        'count': count,
        'count_label': spec.plural_for(count),
        'objects': list(queryset),
        'label': spec.plural_for(count),
        'cascade': [],
    })


@require_open
def duplicate(request, model_key, pk):
    """Copy a record as a starting point for a new one."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

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
    clone.save()
    messages.success(request, f'Copied to a new {spec.singular_lower}. Give it a name, then save.')
    return redirect(reverse('controlpanel:record_edit', args=[spec.key, clone.pk]))


@require_open
def toggle_flag(request, model_key, pk, field_name):
    """Flip a boolean from the table without opening the full form."""
    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    spec = get_spec(model_key)
    if field_name not in spec.form_fields:
        raise Http404

    obj = get_object_or_404(spec.model, pk=pk)
    model_field = spec.model._meta.get_field(field_name)
    if model_field.get_internal_type() != 'BooleanField':
        raise Http404

    setattr(obj, field_name, not getattr(obj, field_name))
    obj.save(update_fields=[field_name])
    messages.info(request, f'{obj}: {field_name} is now {"on" if getattr(obj, field_name) else "off"}.')
    return redirect(request.META.get('HTTP_REFERER') or reverse('controlpanel:records', args=[spec.key]))