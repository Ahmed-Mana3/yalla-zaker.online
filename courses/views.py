from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CourseForm, RoadmapCourseForm, RoadmapForm
from .models import Course, Roadmap, RoadmapCourse


def step_queryset():
    """Every step with its course in one go — no N+1 when progress is read."""
    return RoadmapCourse.objects.select_related('course').order_by('position', 'id')


def roadmap_card_list(roadmaps):
    """Roadmaps plus the numbers the desk, list and detail pages all show."""
    cards = []
    for rm in roadmaps:
        cards.append({
            'roadmap': rm,
            'step_count': rm.step_count(),
            'total_hours': rm.total_planned_hours(),
            'hours_spent': rm.hours_spent(),
            'done_count': rm.completed_count(),
            'tracked_count': rm.tracked_count(),
            'progress': rm.progress(),
        })
    return cards


def prefetched_roadmaps(user):
    return user.roadmaps.prefetch_related(Prefetch('steps', queryset=step_queryset()))


@login_required
def course_index(request):
    courses = request.user.courses.all()
    return render(request, 'courses/index.html', {'courses': courses})


@login_required
def course_create(request):
    initial = None
    source = None
    source_slug = (request.GET.get('from') or '').strip()
    if source_slug:
        source = Course.objects.filter(slug=source_slug, is_public=True).first()
        if source:
            initial = {
                'title': source.title,
                'link': source.link,
                'notes': source.notes,
                'start_date': source.start_date,
                'total_hours': source.total_hours,
            }
    form = CourseForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        course = form.save(commit=False)
        course.owner = request.user
        course.forked_from = source if source and source.owner != request.user else None
        course.save()
        messages.success(request, f'{course.title} added to your desk.')
        return redirect('course_detail', slug=course.slug)
    return render(request, 'courses/form.html', {
        'form': form,
        'heading': 'Add a course',
        'source': source,
    })


@login_required
def course_detail(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if course.owner != request.user:
        if course.is_public:
            messages.info(request, 'This course is shared with you — showing its public page.')
            return redirect('public:course_public', slug=course.slug)
        return render(request, 'courses/access.html', {'course': course}, status=404)
    sessions = course.studysession_set.filter(status='finished').order_by('-ended_at')[:10]
    roadmaps = request.user.roadmaps.filter(steps__course=course).distinct().prefetch_related('steps__course')
    return render(request, 'courses/detail.html', {
        'course': course,
        'sessions': sessions,
        'roadmaps': roadmaps,
    })


@login_required
def course_edit(request, slug):
    course = get_object_or_404(Course, slug=slug, owner=request.user)
    form = CourseForm(request.POST or None, instance=course)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Course saved.')
        return redirect('course_detail', slug=course.slug)
    return render(request, 'courses/form.html', {'form': form, 'heading': 'Edit course', 'course': course})


@login_required
def course_delete(request, slug):
    course = get_object_or_404(Course, slug=slug, owner=request.user)
    if request.method == 'POST':
        course.delete()
        messages.info(request, f'{course.title} removed.')
        return redirect('courses')
    return render(request, 'courses/confirm_delete.html', {'course': course})


def course_public(request, slug):
    """A anyone-with-the-link view of a course. Unauthenticated friendly."""
    course = get_object_or_404(Course, slug=slug, is_public=True)
    live = course.studysession_set.filter(status__in=['active', 'paused']).first()
    if live:
        live.refresh_lifecycle()
    return render(request, 'courses/public.html', {'course': course, 'live': live})


# ---------------------------------------------------------------- roadmaps


@login_required
def roadmap_index(request):
    cards = roadmap_card_list(prefetched_roadmaps(request.user))
    return render(request, 'courses/roadmap_list.html', {'roadmaps': cards})


@login_required
def roadmap_create(request):
    form = RoadmapForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        roadmap = form.save(commit=False)
        roadmap.owner = request.user
        roadmap.save()
        messages.success(request, f'{roadmap.title} — roadmap created. Add courses to it next.')
        return redirect('roadmap_detail', slug=roadmap.slug)
    return render(request, 'courses/roadmap_form.html', {'form': form, 'heading': 'New roadmap'})


@login_required
def roadmap_detail(request, slug):
    roadmap = get_object_or_404(prefetched_roadmaps(request.user), slug=slug)
    return render(request, 'courses/roadmap_detail.html', roadmap_context(roadmap))


def roadmap_context(roadmap):
    """The roadmap page: every course with its own progress and its own actions."""
    steps = list(roadmap.steps.all())
    return {
        'roadmap': roadmap,
        'steps': steps,
        'total_hours': round(roadmap.total_planned_hours(), 1),
        'hours_spent': roadmap.hours_spent(),
        'progress': roadmap.progress(),
        'done_count': roadmap.completed_count(),
        'tracked_count': roadmap.tracked_count(),
    }


@login_required
def roadmap_edit(request, slug):
    roadmap = get_object_or_404(Roadmap, slug=slug, owner=request.user)
    form = RoadmapForm(request.POST or None, instance=roadmap)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Roadmap saved.')
        return redirect('roadmap_detail', slug=roadmap.slug)
    return render(request, 'courses/roadmap_form.html', {'form': form, 'heading': 'Edit roadmap', 'roadmap': roadmap})


@login_required
def roadmap_delete(request, slug):
    roadmap = get_object_or_404(Roadmap, slug=slug, owner=request.user)
    if request.method == 'POST':
        roadmap.delete()
        messages.info(request, 'Roadmap removed.')
        return redirect('roadmaps')
    return render(request, 'courses/roadmap_confirm_delete.html', {'roadmap': roadmap})


@login_required
def roadmap_steps_edit(request, slug):
    roadmap = get_object_or_404(prefetched_roadmaps(request.user), slug=slug)
    return render(request, 'courses/roadmap_steps.html', roadmap_context(roadmap))


@login_required
def roadmap_add_step(request, slug):
    """Add a course directly to this roadmap."""
    roadmap = get_object_or_404(Roadmap, slug=slug, owner=request.user)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json'
    if request.method != 'POST':
        return redirect('roadmap_steps_edit', slug=roadmap.slug)
    title = request.POST.get('title', '').strip()
    link = request.POST.get('link', '').strip()
    if not title or not link:
        if is_ajax:
            return JsonResponse({'ok': False, 'error': 'Course title and link are required.'}, status=400)
        messages.error(request, 'Course title and link are required.')
        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('roadmap_steps_edit', slug=roadmap.slug)
    try:
        hours = max(0.0, float(request.POST.get('planned_hours') or 0))
    except (TypeError, ValueError):
        hours = 0.0
    last = roadmap.steps.order_by('-position').first()
    step = roadmap.steps.create(
        course=None,
        course_title_override=title,
        planned_hours=hours,
        link=link,
        position=(last.position + 1) if last else 0,
    )
    if is_ajax:
        return JsonResponse({
            'ok': True,
            'step': {
                'id': step.id,
                'title': step.display_title(),
                'link': step.link,
                'planned_hours': step.planned_hours,
                'position': step.position,
            }
        })
    messages.success(request, f'{title} added to the roadmap.')
    next_url = request.POST.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('roadmap_steps_edit', slug=roadmap.slug)


@login_required
def roadmap_add_course(request, slug):
    """Direct alias to adding a course to roadmap."""
    if request.method == 'POST':
        return roadmap_add_step(request, slug)
    return redirect('roadmap_steps_edit', slug=slug)


@login_required
def roadmap_remove_step(request, slug, step_id):
    roadmap = get_object_or_404(Roadmap, slug=slug, owner=request.user)
    step = get_object_or_404(RoadmapCourse, pk=step_id, roadmap=roadmap)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json'
    if request.method == 'POST':
        step.delete()
        for position, remaining in enumerate(roadmap.steps.all()):
            if remaining.position != position:
                remaining.position = position
                remaining.save(update_fields=['position'])
        if is_ajax:
            return JsonResponse({'ok': True, 'step_id': step_id})
        messages.info(request, 'Course removed from roadmap.')
    next_url = request.POST.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('roadmap_steps_edit', slug=roadmap.slug)


@login_required
def roadmap_edit_step(request, slug, step_id):
    roadmap = get_object_or_404(Roadmap, slug=slug, owner=request.user)
    step = get_object_or_404(RoadmapCourse, pk=step_id, roadmap=roadmap)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json'
    form = RoadmapCourseForm(request.POST or None, instance=step)
    if request.method == 'POST':
        if form.is_valid():
            form.save()
            if is_ajax:
                return JsonResponse({
                    'ok': True,
                    'step': {
                        'id': step.id,
                        'title': step.display_title(),
                        'link': step.link,
                        'planned_hours': step.planned_hours,
                    }
                })
            messages.success(request, 'Course details updated.')
        else:
            if is_ajax:
                return JsonResponse({'ok': False, 'errors': form.errors}, status=400)
            messages.error(request, 'Could not save course changes.')
    next_url = request.POST.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('roadmap_steps_edit', slug=roadmap.slug)


@login_required
def roadmap_reorder(request, slug):
    roadmap = get_object_or_404(Roadmap, slug=slug, owner=request.user)
    if request.method == 'POST':
        order = request.POST.get('order', '')
        ids = [int(raw) for raw in order.split(',') if raw.strip().isdigit()]
        valid_ids = set(roadmap.steps.values_list('id', flat=True))
        for position, step_id in enumerate(ids):
            if step_id in valid_ids:
                roadmap.steps.filter(pk=step_id).update(position=position)
        return JsonResponse({'ok': True, 'count': len(ids)})
    return JsonResponse({'ok': False}, status=405)


@login_required
def roadmap_clone(request, slug):
    source = get_object_or_404(Roadmap.objects.prefetch_related(Prefetch('steps', queryset=step_queryset())), slug=slug)
    if not (source.is_public or source.owner == request.user):
        return redirect('roadmaps')
    if request.method == 'POST':
        clone = Roadmap.objects.create(
            owner=request.user,
            title=source.title,
            description=source.description,
            is_public=False,
            forked_from=source,
        )
        for step in source.steps.all():
            RoadmapCourse.objects.create(
                roadmap=clone,
                course=None,
                course_title_override=step.display_title(),
                planned_hours=step.planned_hours,
                link=step.link or (step.course.link if step.course else ''),
                position=step.position,
            )
        messages.success(request, f'{source.title} cloned to your roadmaps.')
        return redirect('roadmap_detail', slug=clone.slug)
    return render(request, 'courses/roadmap_public.html', public_roadmap_context(source))


def public_roadmap_context(roadmap):
    steps = list(roadmap.steps.all())
    return {
        'roadmap': roadmap,
        'steps': steps,
        'total_hours': round(sum(s.planned_hours for s in steps), 1),
        'progress': roadmap.progress(),
        'done_count': sum(1 for s in steps if s.is_complete()),
    }


@login_required
def roadmap_fork_step(request, slug, step_id):
    """Copy one course out of the roadmap onto the owner's own desk.

    The step stays in the roadmap and now follows the owner's copy, so the roadmap
    keeps reporting progress while the course tracks hours on its own.
    """
    roadmap = get_object_or_404(Roadmap, slug=slug, owner=request.user)
    step = get_object_or_404(RoadmapCourse, pk=step_id, roadmap=roadmap)
    source = step.course

    if source and source.owner == request.user:
        messages.info(request, f'{source.title} is already on your desk.')
        return redirect('course_detail', slug=source.slug)

    if request.method != 'POST':
        return redirect('roadmap_detail', slug=roadmap.slug)

    course = Course.objects.create(
        owner=request.user,
        title=step.display_title(),
        link=step.link or (source.link if source else ''),
        notes=f'Forked from the roadmap "{roadmap.title}".',
        total_hours=step.planned_hours or (source.total_hours if source else 0),
        is_public=False,
        forked_from=source,
    )
    step.course = course
    step.save(update_fields=['course'])
    messages.success(
        request,
        f'{course.title} is yours now — track it on your desk while the roadmap keeps counting it.',
    )
    next_url = request.POST.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('course_detail', slug=course.slug)


@login_required
def roadmap_step_progress(request, slug, step_id):
    """Tick a roadmap-only course as done (or un-done) by hand.

    A course linked to a real one reports its own progress, so nothing to set here.
    """
    roadmap = get_object_or_404(Roadmap, slug=slug, owner=request.user)
    step = get_object_or_404(RoadmapCourse, pk=step_id, roadmap=roadmap)
    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json'

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST only.'}, status=405)

    if step.is_tracked():
        payload = {'ok': False, 'error': 'This course tracks its own hours from its course page.'}
        if is_ajax:
            return JsonResponse(payload, status=400)
        messages.info(request, payload['error'])
        return redirect('roadmap_detail', slug=roadmap.slug)

    raw = (request.POST.get('progress_percent') or '').strip()
    if raw:
        try:
            value = min(100, max(0, int(float(raw))))
        except (TypeError, ValueError):
            value = step.progress_percent
    else:
        value = 0 if step.is_complete() else 100
    step.progress_percent = value
    step.save(update_fields=['progress_percent'])

    if is_ajax:
        return JsonResponse({'ok': True, 'step_id': step.id, 'progress': step.progress()})
    messages.success(request, f'{step.display_title()} marked as done.' if value >= 100 else f'{step.display_title()} marked as not done.')
    next_url = request.POST.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('roadmap_detail', slug=roadmap.slug)


def roadmap_public(request, slug):
    """Anyone-with-the-link read-only roadmap."""
    roadmap = get_object_or_404(
        Roadmap.objects.prefetch_related(Prefetch('steps', queryset=step_queryset())),
        slug=slug,
        is_public=True,
    )
    return render(request, 'courses/roadmap_public.html', public_roadmap_context(roadmap))
