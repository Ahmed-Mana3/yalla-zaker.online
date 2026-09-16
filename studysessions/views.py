from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from courses.models import Course

from .models import StudySession


def _current(request):
    session = StudySession.current_for(request.user)
    if session:
        if session.status == StudySession.STATUS_ACTIVE and session.target_minutes and \
                session.study_seconds() >= session.target_minutes * 60:
            session.finish()
        elif session.status == StudySession.STATUS_PAUSED:
            session.refresh_lifecycle()
    return session


@login_required
def study_index(request):
    session = _current(request)
    courses = [c for c in request.user.courses.all()[:20] if c.is_active_course()]
    recent = request.user.study_sessions.filter(status='finished').order_by('-ended_at')[:8]
    pending = StudySession.objects.filter(
        user=request.user, status='finished', checked_in=False, course__isnull=False
    ).order_by('-ended_at').first()

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_sessions = request.user.study_sessions.filter(status='finished', ended_at__gte=today_start)
    today_seconds = sum(s.duration_seconds for s in today_sessions)
    today_count = today_sessions.count()

    ctx = {
        'session': session,
        'pending': pending,
        'courses': courses,
        'recent': recent,
        'today_seconds': today_seconds,
        'today_count': today_count,
        'max_break_minutes': settings.MAX_BREAK_MINUTES,
    }
    return render(request, 'studysessions/index.html', ctx)


@login_required
def session_start(request):
    if request.method != 'POST':
        return redirect('study')
    if _current(request):
        messages.warning(request, 'You already have a running session. Finish or resume it first.')
        return redirect('study')
    course = None
    course_id = request.POST.get('course') or ''
    if course_id:
        course = get_object_or_404(Course, pk=course_id, owner=request.user)
    target = None
    raw = (request.POST.get('target') or '').strip()
    if raw:
        try:
            target = min(max(int(raw), 1), 720)
        except ValueError:
            target = None
    session = StudySession.objects.create(user=request.user, course=course, target_minutes=target)
    from .models import StudySegment
    StudySegment.objects.create(session=session)
    if target:
        messages.success(request, f'Focus mode on — {target} minutes on the lamp.')
    else:
        messages.success(request, 'Focus mode on — free focus, no timer.')
    return redirect('study')


@login_required
def session_pause(request):
    if request.method != 'POST':
        return redirect('study')
    session = _current(request)
    if session and session.pause():
        messages.info(request, 'Break starts now. You have 30 minutes — then the session dies.')
    return redirect('study')


@login_required
def session_resume(request):
    if request.method != 'POST':
        return redirect('study')
    session = _current(request)
    if session:
        result = session.resume()
        if result == 'ended':
            messages.warning(request, 'Your break lasted too long. Session ended — the clock counts what you earned.')
        else:
            messages.success(request, 'Back at it.')
    return redirect('study')


@login_required
def session_end(request):
    if request.method != 'POST':
        return redirect('study')
    session = _current(request)
    if session:
        has_course = bool(session.course)
        session.finish()
        ms = session.duration_seconds / 60
        if has_course:
            messages.success(request, f'Session finished — {ms:.0f} min clocked. How many hours did you finish from the course?')
        else:
            session.checked_in = True
            session.save()
            messages.success(request, f'Session finished — {ms:.0f} min of free focus logged.')
    return redirect('study')


@login_required
def session_log(request):
    """Check-in after a course session: ask how many course minutes/hours were completed."""
    if request.method != 'POST':
        return redirect('study')
    s = get_object_or_404(
        StudySession, pk=request.POST.get('session_id') or 0, user=request.user,
        status='finished', checked_in=False, course__isnull=False)

    if request.POST.get('action') == 'skip':
        s.confirm_log(0)
        messages.info(request, f'No course time credited to “{s.course.title}”.')
        return redirect('study')

    raw_minutes = (request.POST.get('minutes') or '').strip()
    raw_hours = (request.POST.get('hours') or '').strip()

    total_hours = 0.0
    has_input = False
    if raw_hours:
        try:
            total_hours += max(0.0, float(raw_hours))
            has_input = True
        except ValueError:
            pass
    if raw_minutes:
        try:
            total_hours += max(0.0, float(raw_minutes) / 60.0)
            has_input = True
        except ValueError:
            pass

    if not has_input:
        total_hours = s.clocked_hours


    seconds = int(round(total_hours * 3600))
    s.confirm_log(seconds)

    if total_hours > 0:
        course = s.course
        mins_display = int(round(total_hours * 60))
        if not course.is_active_course():
            messages.success(
                request,
                f'🎉 Outstanding! You logged {mins_display} min ({total_hours:g}h) and completed “{course.title}”!'
            )
        else:
            messages.success(
                request,
                f'{mins_display} min ({total_hours:g}h) added to “{course.title}”. {course.remaining_hours():g}h remaining.'
            )
    else:
        messages.info(request, f'Nothing logged to “{s.course.title}” this time.')
    return redirect('study')




@login_required
def session_state_api(request):
    """Lightweight JSON for the timer so the page can tick without reloading."""
    session = _current(request)
    payload = {'session': None}
    if session:
        now = timezone.now()
        payload['session'] = {
            'id': session.id,
            'status': session.status,
            'elapsed': session.study_seconds(),
            'breaks': int(session.break_seconds()),
            'started_at': session.started_at.isoformat(),
            'paused_at': None,
            'max_break': settings.MAX_BREAK_MINUTES,
            'target': session.target_minutes,
            'course': session.course.title if session.course else 'Focus',
        }
        break_seg = session.break_segments.filter(ended_at__isnull=True).first()
        if break_seg:
            payload['session']['paused_at'] = break_seg.started_at.isoformat()
            payload['session']['break_left'] = max(
                0, int(settings.MAX_BREAK_MINUTES * 60 - (now - break_seg.started_at).total_seconds()))
    return JsonResponse(payload)