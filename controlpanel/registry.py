"""Model registry for the exclusive control panel.

Every model exposed on the panel is declared once here: which columns the table
shows, how the record is labelled, which fields are editable, and what a search
matches. Adding a model to the panel means adding one ``ModelSpec`` to
``REGISTRY`` — no view or template changes required.

Column kinds
------------
``text`` ``num`` ``bool`` ``date`` ``datetime`` ``choice`` ``url`` ``rel``
``minutes`` — a duration stored in seconds but always shown in minutes.
``count``    — the number of rows on the other side of a relation.

Time is stored in seconds (``StudySession.duration_seconds``) because that is
what the clock produces, but the panel only ever writes or displays minutes. A
field named in ``ModelSpec.minute_fields`` is rendered as minutes in the table
and accepted as minutes in the form, then converted back to seconds on save.
"""

from dataclasses import dataclass
from typing import Any

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Q

User = get_user_model()

SECONDS_PER_MINUTE = 60


def as_minutes(seconds) -> int:
    """Whole minutes for a seconds count. ``None``/blank stays ``None``."""
    if seconds in (None, ''):
        return None
    return max(0, round(float(seconds) / SECONDS_PER_MINUTE))


@dataclass(frozen=True)
class Column:
    """One column in the records table."""

    field: str
    label: str
    kind: str = 'text'  # text | num | bool | date | datetime | choice | url | rel | minutes | count


@dataclass(frozen=True)
class ModelSpec:
    key: str
    model_label: str
    title: str
    singular: str
    blurb: str
    group: str
    columns: tuple
    form_fields: tuple = ()
    search: tuple = ()
    ordering: tuple = ()
    # Fields stored in seconds but shown and edited as minutes.
    minute_fields: tuple = ()
    danger: str = ''
    special_form: str = ''

    @property
    def model(self):
        return apps.get_model(self.model_label)

    @property
    def singular_lower(self):
        return self.singular.lower()

    @property
    def minute_field_set(self):
        return frozenset(self.minute_fields)

    def _forward_relations(self, model, skip=()):
        """Single-valued relations on ``model``, ignoring self-references."""
        return [
            f for f in model._meta.fields
            if (f.many_to_one or f.one_to_one) and f.name not in skip
        ]

    @property
    def select_related_fields(self):
        """Forward relations to fetch with the row so FK columns cost no query.

        Column fields may walk a path (``session__user``). One extra hop is
        followed past each of them because that is what ``__str__`` usually
        reaches for — ``str(Course)`` prints its owner, so rendering the course
        column would otherwise query per row.
        """
        out = []
        for col in self.columns:
            if col.kind != 'rel' or col.field in out:
                continue
            root = col.field.split('__', 1)[0]
            field = self.model._meta.get_field(root)
            if not (field.many_to_one or field.one_to_one):
                continue
            out.append(col.field)
            target = field.related_model
            skip = {col.field.split('__')[-1]} if '__' in col.field else set()
            for nested in self._forward_relations(target, skip=skip):
                path = f'{col.field}__{nested.name}'
                if path not in out:
                    out.append(path)
        return tuple(out)

    @property
    def prefetch_fields(self):
        """Relations whose row count is shown, prefetched to stay one query each."""
        return tuple(
            col.field for col in self.columns
            if col.kind == 'count' and col.field not in self.select_related_fields
        )

    @property
    def toggle_fields(self):
        """Booleans the panel can flip straight from the table."""
        out = []
        for col in self.columns:
            if col.kind != 'bool' or col.field not in self.form_fields:
                continue
            field = self.model._meta.get_field(col.field)
            if field.get_internal_type() == 'BooleanField':
                out.append(col.field)
        return tuple(out)

    @property
    def blocked_unique_fields(self):
        """Required unique fields the copy would have to leave blank.

        Copying those would either collide with the row they came from or fail on
        an empty value, so a spec with any of them is not duplicable.
        """
        out = []
        for name in self.unique_fields():
            if name not in self.form_fields:
                continue
            field = self.model._meta.get_field(name)
            if not field.blank and not field.null:
                out.append(name)
        return out

    @property
    def can_duplicate(self):
        return bool(self.copyable_fields()) and not self.blocked_unique_fields

    def plural_for(self, count):
        """“1 course” / “3 courses” — the singular/plural already written out."""
        return f'{count} {self.singular_lower if count == 1 else self.title.lower()}'

    def unique_fields(self):
        """Field names covered by a unique constraint, copied or not."""
        names = {f.name for f in self.model._meta.fields if f.unique}
        for constraint in self.model._meta.constraints:
            names.update(getattr(constraint, 'fields', ()) or ())
        return names

    def copyable_fields(self):
        """Editable fields safe to carry onto a duplicate of a record."""
        blocked = self.unique_fields()
        out = []
        for name in self.form_fields:
            if name in blocked:
                continue
            field = self.model._meta.get_field(name)
            if getattr(field, 'auto_now', False) or getattr(field, 'auto_now_add', False):
                continue
            if not field.editable or not field.concrete:
                continue
            out.append(name)
        return out

    def get_queryset(self):
        qs = self.model._default_manager.all()
        if self.select_related_fields:
            qs = qs.select_related(*self.select_related_fields)
        if self.prefetch_fields:
            qs = qs.prefetch_related(*self.prefetch_fields)
        ordering = self.ordering or tuple(self.model._meta.ordering or ('-pk',))
        # Prefetch_related needs a concrete ordering or it warns; pk breaks ties
        # so paging is stable even when the model's own ordering is ambiguous.
        return qs.order_by(*ordering)

    def search_queryset(self, queryset, term):
        """Filter by the spec's search paths, falling back to an exact pk hit.

        Every search path is a forward relation, so the joins cannot fan rows
        out — no DISTINCT needed, and adding one would break the related-field
        ordering that PostgreSQL rejects.
        """
        term = (term or '').strip()
        if not term:
            return queryset
        clause = Q()
        for path in self.search:
            clause |= Q(**{f'{path}__icontains': term})
        if term.isdigit():
            clause |= Q(pk=int(term))
        if not self.search:
            return queryset.filter(pk=term) if term.isdigit() else queryset.none()
        return queryset.filter(clause)

    def cascade_targets(self, obj) -> list:
        """Reverse relations touched when ``obj`` is deleted.

        CASCADE rows disappear; SET_NULL rows survive with the pointer cleared.
        Reporting both is the difference between “this is safe” and “you have
        not read the consequences”.
        """
        out = []
        for rel in obj._meta.related_objects:
            if rel.one_to_many is False and rel.one_to_one is False:
                continue  # many-to-many: nothing is deleted with the parent
            action = getattr(rel.field.remote_field.on_delete, '__name__', '')
            if action not in ('CASCADE', 'SET_NULL'):
                continue
            accessor = rel.get_accessor_name()
            try:
                related = getattr(obj, accessor)
                count = related.count() if hasattr(related, 'count') else 1
            except ObjectDoesNotExist:
                count = 0
            except (AttributeError, TypeError, ValueError):
                continue
            if not count:
                continue
            out.append({
                'label': str(rel.related_model._meta.verbose_name_plural),
                'count': count,
                'rel': accessor,
                'deletes': action == 'CASCADE',
            })
        return sorted(out, key=lambda item: (-item['count'], item['label']))

    def bulk_cascade_targets(self, objects) -> list:
        """Cascade impact of several records at once, merged by related model."""
        merged = {}
        for obj in objects:
            for item in self.cascade_targets(obj):
                slot = merged.setdefault(item['label'], {'label': item['label'], 'count': 0, 'deletes': item['deletes']})
                slot['count'] += item['count']
        return sorted(merged.values(), key=lambda item: (-item['count'], item['label']))

    def row_cells(self, obj) -> list:
        cells = []
        for col in self.columns:
            cells.append(self.cell(obj, col))
        return cells

    def resolve(self, obj, path):
        """Walk a possibly-dotted field path, stopping clean at a null relation."""
        value = obj
        for part in path.split('__'):
            if value is None:
                return None
            value = getattr(value, part, None)
        return value

    def cell(self, obj, col) -> dict:
        value: Any = self.resolve(obj, col.field)
        kind = col.kind
        base = {'label': col.label, 'field': col.field}
        if kind == 'bool':
            return {**base, 'kind': 'bool', 'on': bool(value), 'value': 'yes' if value else 'no'}
        if kind == 'count':
            try:
                related = getattr(obj, col.field)
                total = related.count() if hasattr(related, 'count') else 0
            except ObjectDoesNotExist:
                total = 0
            return {**base, 'kind': 'num', 'value': total}
        if kind == 'minutes':
            minutes = as_minutes(value)
            return {**base, 'kind': 'num', 'value': '—' if minutes is None else minutes}
        if kind in ('rel', 'text', 'choice') and value not in ('', None):
            return {**base, 'kind': 'text', 'value': str(value)}
        if kind == 'url':
            return {**base, 'kind': kind, 'value': value or '', 'on': bool(value)}
        if kind == 'datetime':
            return {**base, 'kind': kind, 'value': value.strftime('%Y-%m-%d %H:%M') if value else '—'}
        if kind == 'date':
            return {**base, 'kind': kind, 'value': value.strftime('%Y-%m-%d') if value else '—'}
        if kind == 'num':
            return {**base, 'kind': kind, 'value': '—' if value in ('', None) else value}
        return {**base, 'kind': 'text', 'value': '—' if value in ('', None) else str(value)}


C = Column

USER_COLUMNS = (
    C('username', 'Username'),
    C('email', 'Email'),
    C('is_active', 'Active', 'bool'),
    C('is_staff', 'Staff', 'bool'),
    C('date_joined', 'Joined', 'datetime'),
    C('last_login', 'Last login', 'datetime'),
)

REGISTRY = (
    ModelSpec(
        key='user',
        model_label='auth.User',
        title='Users',
        singular='User',
        blurb='Every account on the site. Deleting one removes everything they own.',
        group='People',
        columns=(
            C('username', 'Username'),
            C('email', 'Email'),
            C('is_active', 'Active', 'bool'),
            C('is_staff', 'Staff', 'bool'),
            C('is_superuser', 'Superuser', 'bool'),
            C('courses', 'Courses', 'count'),
            C('date_joined', 'Joined', 'datetime'),
            C('last_login', 'Last login', 'datetime'),
        ),
        form_fields=('username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'is_superuser'),
        search=('username', 'email', 'first_name', 'last_name'),
        ordering=('-date_joined',),
        special_form='user',
        danger='Cascades: profile, courses, roadmaps, sessions, challenges, friendships.',
    ),
    ModelSpec(
        key='profile',
        model_label='accounts.Profile',
        title='Profiles',
        singular='Profile',
        blurb='The public card behind each account — bio, avatar colour and presence.',
        group='People',
        columns=(
            C('user', 'User', 'rel'),
            C('bio', 'Bio'),
            C('avatar_hue', 'Hue', 'num'),
            C('last_seen', 'Last seen', 'datetime'),
        ),
        form_fields=('user', 'bio', 'avatar_hue'),
        search=('user__username', 'bio'),
        danger='Cascades: nothing further.',
    ),
    ModelSpec(
        key='friendship',
        model_label='accounts.Friendship',
        title='Friendships',
        singular='Friendship',
        blurb='The link between two accounts — pending, accepted or declined.',
        group='People',
        columns=(
            C('from_user', 'From', 'rel'),
            C('to_user', 'To', 'rel'),
            C('status', 'Status', 'choice'),
            C('created_at', 'Created', 'datetime'),
            C('updated_at', 'Updated', 'datetime'),
        ),
        form_fields=('from_user', 'to_user', 'status'),
        search=('from_user__username', 'to_user__username'),
        danger='Cascades: nothing further.',
    ),
    ModelSpec(
        key='course',
        model_label='courses.Course',
        title='Courses',
        singular='Course',
        blurb='A course on someone’s desk, with its planned and earned hours.',
        group='Study',
        columns=(
            C('title', 'Course'),
            C('owner', 'Owner', 'rel'),
            C('link', 'Link', 'url'),
            C('total_hours', 'Planned h', 'num'),
            C('hours_done', 'Earned h', 'num'),
            C('is_public', 'Public', 'bool'),
            C('studysession_set', 'Sessions', 'count'),
            C('start_date', 'Starts', 'date'),
            C('end_date', 'Ends', 'date'),
            C('created_at', 'Created', 'datetime'),
        ),
        form_fields=('owner', 'title', 'link', 'notes', 'start_date', 'end_date', 'total_hours', 'hours_done', 'is_public', 'forked_from'),
        search=('title', 'owner__username', 'notes'),
        danger='Study sessions keep their history; the course pointer is cleared.',
    ),
    ModelSpec(
        key='roadmap',
        model_label='courses.Roadmap',
        title='Roadmaps',
        singular='Roadmap',
        blurb='An ordered group of courses that lead to one goal.',
        group='Study',
        columns=(
            C('title', 'Roadmap'),
            C('owner', 'Owner', 'rel'),
            C('description', 'Description'),
            C('is_public', 'Public', 'bool'),
            C('steps', 'Steps', 'count'),
            C('created_at', 'Created', 'datetime'),
        ),
        form_fields=('owner', 'title', 'description', 'is_public', 'forked_from'),
        search=('title', 'owner__username', 'description'),
        danger='Cascades: every step inside the roadmap.',
    ),
    ModelSpec(
        key='roadmapcourse',
        model_label='courses.RoadmapCourse',
        title='Roadmap steps',
        singular='Roadmap step',
        blurb='One ordered step inside a roadmap.',
        group='Study',
        columns=(
            C('roadmap', 'Roadmap', 'rel'),
            C('course', 'Course', 'rel'),
            C('position', 'Position', 'num'),
            C('planned_hours', 'Planned h', 'num'),
            C('progress_percent', 'Progress %', 'num'),
            C('link', 'Link', 'url'),
        ),
        form_fields=('roadmap', 'course', 'position', 'course_title_override', 'planned_hours', 'link', 'progress_percent'),
        search=('roadmap__title', 'course__title', 'course_title_override'),
        ordering=('roadmap__title', 'position', 'id'),
        danger='Cascades: nothing further. A linked course keeps its own history.',
    ),
    ModelSpec(
        key='challenge',
        model_label='challenges.Challenge',
        title='Challenges',
        singular='Challenge',
        blurb='A dated contest everyone can join; the score is the longest session.',
        group='Community',
        columns=(
            C('title', 'Challenge'),
            C('created_by', 'Created by', 'rel'),
            C('starts_at', 'Starts', 'date'),
            C('ends_at', 'Ends', 'date'),
            C('members', 'Members', 'count'),
            C('created_at', 'Created', 'datetime'),
        ),
        form_fields=('title', 'description', 'created_by', 'starts_at', 'ends_at'),
        search=('title', 'description', 'created_by__username'),
        danger='Cascades: every membership row.',
    ),
    ModelSpec(
        key='challengemember',
        model_label='challenges.ChallengeMember',
        title='Challenge members',
        singular='Challenge member',
        blurb='Who joined which challenge, and when.',
        group='Community',
        columns=(
            C('challenge', 'Challenge', 'rel'),
            C('user', 'Member', 'rel'),
            C('joined_at', 'Joined', 'datetime'),
        ),
        form_fields=('challenge', 'user'),
        search=('challenge__title', 'user__username'),
        danger='Cascades: nothing further.',
    ),
    ModelSpec(
        key='studysession',
        model_label='studysessions.StudySession',
        title='Study sessions',
        singular='Study session',
        blurb='Every clock run on the lamp, finished or still going.',
        group='Study',
        columns=(
            C('user', 'User', 'rel'),
            C('course', 'Course', 'rel'),
            C('status', 'Status', 'choice'),
            C('started_at', 'Started', 'datetime'),
            C('duration_seconds', 'Clocked min', 'minutes'),
            C('manual_seconds', 'Credited min', 'minutes'),
            C('target_minutes', 'Target min', 'num'),
            C('checked_in', 'Checked in', 'bool'),
            C('study_segments', 'Study blocks', 'count'),
            C('break_segments', 'Breaks', 'count'),
            C('ended_at', 'Ended', 'datetime'),
        ),
        form_fields=('user', 'course', 'status', 'started_at', 'ended_at', 'duration_seconds',
                     'target_minutes', 'checked_in', 'manual_seconds'),
        minute_fields=('duration_seconds', 'manual_seconds'),
        search=('user__username', 'course__title'),
        danger='Cascades: every study and break segment inside the session.',
    ),
    ModelSpec(
        key='studysegment',
        model_label='studysessions.StudySegment',
        title='Study segments',
        singular='Study segment',
        blurb='The raw focus blocks that make up a session.',
        group='Study',
        columns=(
            C('session', 'Session', 'rel'),
            C('session__user', 'User', 'rel'),
            C('started_at', 'Started', 'datetime'),
            C('ended_at', 'Ended', 'datetime'),
            # StudySegment.minutes is already minutes, so it needs no conversion.
            C('minutes', 'Length min', 'num'),
        ),
        form_fields=('session', 'started_at', 'ended_at'),
        search=('session__user__username',),
        danger='Cascades: nothing further. The session total is not recalculated here.',
    ),
    ModelSpec(
        key='breaksegment',
        model_label='studysessions.BreakSegment',
        title='Break segments',
        singular='Break segment',
        blurb='The pauses between focus blocks.',
        group='Study',
        columns=(
            C('session', 'Session', 'rel'),
            C('session__user', 'User', 'rel'),
            C('started_at', 'Started', 'datetime'),
            C('ended_at', 'Ended', 'datetime'),
            C('minutes', 'Length min', 'num'),
        ),
        form_fields=('session', 'started_at', 'ended_at'),
        search=('session__user__username',),
        danger='Cascades: nothing further. The session total is not recalculated here.',
    ),
    ModelSpec(
        key='group',
        model_label='auth.Group',
        title='Permission groups',
        singular='Permission group',
        blurb='Django permission bundles. Only these can reach /admin/ once Staff is on.',
        group='People',
        columns=(
            C('name', 'Group'),
            C('permissions', 'Permissions', 'count'),
        ),
        form_fields=('name', 'permissions'),
        search=('name',),
        danger='Staff accounts lose the permissions in this group immediately.',
    ),
)

REGISTRY_BY_KEY = {spec.key: spec for spec in REGISTRY}
GROUPS = []
for _spec in REGISTRY:
    if _spec.group not in GROUPS:
        GROUPS.append(_spec.group)

GROUP_BLURBS = {
    'People': 'Accounts and the links between them.',
    'Study': 'Courses, roadmaps and clocked focus time.',
    'Community': 'Challenges and their members.',
}


def get_spec(key: str):
    from django.http import Http404

    spec = REGISTRY_BY_KEY.get(key)
    if spec is None:
        raise Http404('That record type is not on the panel.')
    return spec


def counts() -> dict:
    """``{spec.key: row count}`` for every registered model.

    The sidebar and the dashboard both need this, so it is computed once per
    request and cached on the request object by the context processor.
    """
    return {spec.key: spec.model._default_manager.count() for spec in REGISTRY}


def request_counts(request) -> dict:
    """Counts for this request, computed at most once."""
    cached = getattr(request, '_cp_counts', None)
    if cached is None:
        cached = counts()
        request._cp_counts = cached
    return cached


def totals(counts_by_key: dict = None) -> list:
    """Row count per model, for the dashboard.

    Pass the request's cached ``counts()`` to avoid re-running every COUNT.
    """
    by_key = counts_by_key if counts_by_key is not None else counts()
    return [{'spec': spec, 'count': by_key.get(spec.key, 0)} for spec in REGISTRY]