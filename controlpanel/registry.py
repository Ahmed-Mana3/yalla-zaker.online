"""Model registry for the exclusive control panel.

Every model exposed on the panel is declared once here: which columns the table
shows, how the record is labelled, which fields are editable, and what a search
matches. Adding a model to the panel means adding one ``ModelSpec`` to
``REGISTRY`` — no view or template changes required.
"""

from dataclasses import dataclass
from typing import Any

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


@dataclass(frozen=True)
class Column:
    """One column in the records table."""

    field: str
    label: str
    kind: str = 'text'  # text | num | bool | date | datetime | choice | url | rel


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
    readonly_fields: tuple = ()
    row_template: str = ''
    special_form: str = ''
    danger: str = ''
    icon: str = ''

    @property
    def model(self):
        return apps.get_model(self.model_label)

    @property
    def singular_lower(self):
        return self.singular.lower()

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
        ordering = self.ordering or tuple(self.model._meta.ordering or ('-pk',))
        return qs.order_by(*ordering)

    def search_queryset(self, queryset, term):
        term = term.strip()
        if not term:
            return queryset
        if term.isdigit() and not self.search:
            return queryset.filter(pk=int(term))
        clause = Q()
        hits = False
        for path in self.search:
            clause |= Q(**{f'{path}__icontains': term})
            hits = True
        if hits:
            return queryset.filter(clause).distinct()
        return queryset.filter(pk=term) if term.isdigit() else queryset.none()

    def cascade_targets(self, obj) -> list:
        """Reverse relations that will be wiped when ``obj`` is deleted."""
        out = []
        for rel in obj._meta.related_objects:
            if rel.field.remote_field.on_delete.__name__ != 'CASCADE':
                continue
            accessor = rel.get_accessor_name()
            try:
                count = getattr(obj, accessor).count()
            except (AttributeError, TypeError, ValueError):
                continue
            name = rel.related_model._meta.verbose_name_plural
            out.append({'label': str(name), 'count': count, 'rel': accessor})
        return sorted(out, key=lambda item: -item['count'])

    def row_cells(self, obj) -> list:
        cells = []
        for col in self.columns:
            cells.append(self.cell(obj, col))
        return cells

    def cell(self, obj, col) -> dict:
        value: Any = getattr(obj, col.field, '')
        kind = col.kind
        if kind == 'bool':
            return {'label': col.label, 'kind': kind, 'on': bool(value), 'value': 'Yes' if value else 'No'}
        if kind in ('rel', 'text', 'choice') and value not in ('', None):
            return {'label': col.label, 'kind': 'text', 'value': str(value)}
        if kind == 'url':
            return {'label': col.label, 'kind': kind, 'value': value or '', 'on': bool(value)}
        if kind == 'datetime':
            return {'label': col.label, 'kind': kind, 'value': value.strftime('%Y-%m-%d %H:%M') if value else '—'}
        if kind == 'date':
            return {'label': col.label, 'kind': kind, 'value': value.strftime('%Y-%m-%d') if value else '—'}
        if kind == 'num':
            return {'label': col.label, 'kind': kind, 'value': '—' if value in ('', None) else value}
        return {'label': col.label, 'kind': 'text', 'value': '—' if value in ('', None) else str(value)}


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
        columns=USER_COLUMNS,
        form_fields=('username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff', 'is_superuser'),
        search=('username', 'email', 'first_name', 'last_name'),
        ordering=('-date_joined',),
        special_form='user',
        danger='Cascades: profile, courses, roadmaps, sessions, challenges, friendships.',
        icon='user',
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
        icon='user',
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
        ),
        form_fields=('from_user', 'to_user', 'status'),
        search=('from_user__username', 'to_user__username'),
        danger='Cascades: nothing further.',
        icon='users',
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
            C('total_hours', 'Planned', 'num'),
            C('hours_done', 'Earned', 'num'),
            C('is_public', 'Public', 'bool'),
            C('created_at', 'Created', 'datetime'),
        ),
        form_fields=('owner', 'title', 'link', 'notes', 'start_date', 'end_date', 'total_hours', 'hours_done', 'is_public', 'forked_from'),
        search=('title', 'owner__username', 'notes'),
        danger='Study sessions keep their history; the course pointer is cleared.',
        icon='book',
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
            C('created_at', 'Created', 'datetime'),
        ),
        form_fields=('owner', 'title', 'description', 'is_public', 'forked_from'),
        search=('title', 'owner__username', 'description'),
        danger='Cascades: every step inside the roadmap.',
        icon='map',
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
            C('planned_hours', 'Planned', 'num'),
            C('progress_percent', 'Progress', 'num'),
            C('link', 'Link', 'url'),
        ),
        form_fields=('roadmap', 'course', 'position', 'course_title_override', 'planned_hours', 'link', 'progress_percent'),
        search=('roadmap__title', 'course__title', 'course_title_override'),
        ordering=('roadmap__title', 'position', 'id'),
        icon='map',
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
            C('created_at', 'Created', 'datetime'),
        ),
        form_fields=('title', 'description', 'created_by', 'starts_at', 'ends_at'),
        search=('title', 'description', 'created_by__username'),
        danger='Cascades: every membership row.',
        icon='flag',
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
        icon='flag',
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
            C('duration_seconds', 'Clocked', 'num'),
            C('manual_seconds', 'Credited', 'num'),
        ),
        form_fields=('user', 'course', 'status', 'started_at', 'ended_at', 'duration_seconds',
                     'target_minutes', 'checked_in', 'manual_seconds'),
        search=('user__username', 'course__title'),
        danger='Cascades: every study and break segment inside the session.',
        icon='clock',
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
            C('started_at', 'Started', 'datetime'),
            C('ended_at', 'Ended', 'datetime'),
        ),
        form_fields=('session', 'started_at', 'ended_at'),
        search=('session__user__username',),
        icon='clock',
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
            C('started_at', 'Started', 'datetime'),
            C('ended_at', 'Ended', 'datetime'),
        ),
        form_fields=('session', 'started_at', 'ended_at'),
        search=('session__user__username',),
        icon='clock',
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


def totals() -> list:
    """Row count per model, for the dashboard."""
    out = []
    for spec in REGISTRY:
        out.append({
            'spec': spec,
            'count': spec.model._default_manager.count(),
        })
    return out