from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import CourseForm, RoadmapCourseForm, RoadmapForm
from .models import Course, Roadmap, RoadmapCourse


@login_required
def course_index(request):
    courses = request.user.courses.all()
    return render(request, 'courses/index.html', {'courses': courses})


@login_required
def course_create(request):
    form = CourseForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        course = form.save(commit=False)
        course.owner = request.user
        course.save()
        messages.success(request, f'{course.title} added to your desk.')
        return redirect('course_detail', slug=course.slug)
    return render(request, 'courses/form.html', {'form': form, 'heading': 'Add a course'})


@login_required
def course_detail(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if course.owner != request.user:
        if course.is_public:
            messages.info(request, 'This course is shared with you — showing its public page.')
            return redirect('public:course_public', slug=course.slug)
        return render(request, 'courses/access.html', {'course': course}, status=404)
    sessions = course.studysession_set.filter(status='finished').order_by('-ended_at')[:10]
    return render(request, 'courses/detail.html', {'course': course, 'sessions': sessions})


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
    roadmaps = request.user.roadmaps.prefetch_related('steps').all()
    cards = [
        {
            'roadmap': rm,
            'step_count': rm.step_count(),
            'total_hours': rm.total_planned_hours(),
        }
        for rm in roadmaps
    ]
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
    roadmap = get_object_or_404(Roadmap, slug=slug, owner=request.user)
    steps = roadmap.steps.order_by('position', 'id')
    total_hours = sum(s.planned_hours for s in steps)
    return render(request, 'courses/roadmap_detail.html', {
        'roadmap': roadmap,
        'steps': steps,
        'total_hours': round(total_hours, 1),
    })


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
    roadmap = get_object_or_404(Roadmap, slug=slug, owner=request.user)
    steps = roadmap.steps.order_by('position', 'id')
    total_hours = sum(s.planned_hours for s in steps)
    return render(request, 'courses/roadmap_steps.html', {
        'roadmap': roadmap,
        'steps': steps,
        'total_hours': round(total_hours, 1),
    })


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
    source = get_object_or_404(Roadmap, slug=slug)
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
        for step in source.steps.order_by('position', 'id'):
            RoadmapCourse.objects.create(
                roadmap=clone,
                course=None,
                course_title_override=step.display_title(),
                planned_hours=step.planned_hours,
                link=step.link,
                position=step.position,
            )
        messages.success(request, f'{source.title} cloned to your roadmaps.')
        return redirect('roadmap_detail', slug=clone.slug)
    return render(request, 'courses/roadmap_public.html', {'roadmap': source})


def roadmap_public(request, slug):
    """Anyone-with-the-link read-only roadmap."""
    roadmap = get_object_or_404(Roadmap, slug=slug, is_public=True)
    steps = roadmap.steps.order_by('position', 'id')
    total_hours = sum(s.planned_hours for s in steps)
    return render(request, 'courses/roadmap_public.html', {
        'roadmap': roadmap,
        'steps': steps,
        'total_hours': round(total_hours, 1),
    })