from django.contrib import messages
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from challenges.models import Challenge, ChallengeMember
from courses.models import Course, Roadmap
from studysessions.models import StudySession

from .forms import ProfileForm, SignUpForm
from .models import Friendship, Profile


def online_status(user):
    """(status, label) showing a user's presence and study state.

    - 'live': actively studying right now
    - 'paused': mid break on a running session
    - 'online': on the site recently, not studying
    - 'offline': not seen recently
    """
    live = StudySession.live_for(user)
    if live:
        if live.status == 'active':
            return 'live', 'studying now'
        return 'paused', 'on a break'
    profile = getattr(user, 'profile', None)
    if profile and profile.is_online():
        return 'online', 'online'
    return 'offline', 'offline'


def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'accounts/landing.html')


def signup(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = SignUpForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        messages.success(request, f'Welcome aboard, {user.username}. Add your first course.')
        return redirect('login')
    return render(request, 'accounts/auth.html', {'form': form, 'mode': 'signup'})


def logout_view(request):
    if request.method == 'POST':
        from django.contrib.auth import logout
        logout(request)
        return redirect('home')
    return redirect('home')


@login_required
def dashboard(request):
    user = request.user
    cur = StudySession.current_for(user)
    if cur:
        cur.refresh_lifecycle()

    courses = list(user.courses.all())
    courses.sort(key=lambda c: (
        1 if c.end_date else 0,
        -(c.progress() or 0),
        c.title.lower(),
    ))
    friends = Friendship.friends_of(user)
    today = timezone.now().date()
    active_challenges = Challenge.objects.filter(
        members__user=user, starts_at__lte=today, ends_at__gte=today
    ).distinct()

    friend_rows = []
    for friend in friends:
        live = StudySession.live_for(friend)
        today_sessions = StudySession.objects.filter(
            user=friend, status='finished', started_at__date=today
        )
        status, label = online_status(friend)
        friend_rows.append({
            'friend': friend,
            'live': live,
            'today_count': today_sessions.count(),
            'status': status,
            'label': label,
        })
    status_rank = {'live': 0, 'paused': 1, 'online': 2, 'offline': 3}
    friend_rows.sort(key=lambda r: (status_rank.get(r['status'], 9), r['friend'].username.lower()))

    stats = user.study_sessions.filter(status='finished')
    today_seconds = sum(
        s.duration_seconds for s in stats.filter(started_at__date=today)
    )
    longest = stats.order_by('-duration_seconds').first()
    total_seconds = sum(s.duration_seconds for s in stats)

    challenge_cards = [
        {
            'challenge': challenge,
            'total_seconds': ChallengeMember.member_stats(user, challenge)['total_seconds'],
            'days_left': (challenge.ends_at - today).days,
        }
        for challenge in active_challenges
    ]

    roadmaps = user.roadmaps.prefetch_related('steps').all()
    roadmap_cards = [
        {
            'roadmap': rm,
            'step_count': rm.step_count(),
            'total_hours': rm.total_planned_hours(),
        }
        for rm in roadmaps
    ]

    ctx = {
        'courses': courses,
        'friend_rows': friend_rows,
        'friends_live_count': sum(1 for r in friend_rows if r['status'] in ('live', 'paused')),
        'active_challenges': active_challenges,
        'challenge_cards': challenge_cards,
        'today_seconds': today_seconds,
        'longest': longest,
        'total_seconds': total_seconds,
        'active_session': StudySession.current_for(user),
        'friends': friends,
        'max_break_minutes': settings.MAX_BREAK_MINUTES,
        'roadmap_cards': roadmap_cards,
        'hour': timezone.localtime().hour,
    }
    return render(request, 'accounts/dashboard.html', ctx)


@login_required
def profile_edit(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    form = ProfileForm(request.POST or None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Profile saved.')
        return redirect('profile', username=request.user.username)
    return render(request, 'accounts/profile_edit.html', {'form': form})


def profile_view(request, username):
    user = get_object_or_404(User, username=username)
    live = StudySession.live_for(user)
    is_self = request.user.is_authenticated and user == request.user
    is_friend = request.user.is_authenticated and request.user != user and Friendship.are_friends(request.user, user)
    profile, _ = Profile.objects.get_or_create(user=user)

    # Hours and course progress are shared with the owner and their friends.
    can_see_stats = is_self or is_friend
    if can_see_stats:
        finished = user.study_sessions.filter(status='finished')
        agg = finished.aggregate(total=Sum('duration_seconds'))
        total_seconds = agg['total'] or 0
        today = timezone.now().date()
        today_seconds = sum(
            s.duration_seconds for s in finished.filter(started_at__date=today)
        )
    else:
        total_seconds = 0
        today_seconds = 0

    courses = Course.objects.filter(owner=user)
    if not can_see_stats:
        courses = courses.filter(is_public=True)
    courses = list(courses)

    ctx = {
        'subject': user,
        'profile': profile,
        'live': live,
        'is_online': profile.is_online(),
        'courses': courses,
        'is_friend': is_friend,
        'is_self': is_self,
        'can_see_stats': can_see_stats,
        'total_seconds': total_seconds,
        'today_seconds': today_seconds,
    }
    return render(request, 'accounts/profile.html', ctx)


# ------------------------------------------------------------------- friends


@login_required
def friends_index(request):
    user = request.user
    cur = StudySession.current_for(user)
    if cur:
        cur.refresh_lifecycle()

    friends = Friendship.friends_of(user)
    incoming = Friendship.objects.filter(to_user=user, status=Friendship.STATUS_PENDING)
    outgoing = Friendship.objects.filter(from_user=user, status=Friendship.STATUS_PENDING)

    q = request.GET.get('q', '').strip()
    search = None
    if q:
        search = User.objects.filter(Q(username__icontains=q) | Q(email__icontains=q)).exclude(
            pk=user.pk).distinct()
        with_status = []
        for su in search:
            conn = Friendship.connection(user, su)
            with_status.append({'user': su, 'conn': conn})
        search = with_status

    friend_rows = []
    for friend in friends:
        live = StudySession.live_for(friend)
        status, label = online_status(friend)
        friend_rows.append({'friend': friend, 'live': live, 'status': status, 'label': label})

    ctx = {
        'friends': friend_rows,
        'incoming': incoming,
        'outgoing': outgoing,
        'q': q,
        'search': search,
    }
    return render(request, 'accounts/friends.html', ctx)


@login_required
def friend_request(request, user_id):
    if request.method != 'POST':
        return redirect('friends')
    target = get_object_or_404(User, pk=user_id)
    if target == request.user:
        messages.warning(request, 'You can’t befriend yourself.')
        return redirect('friends')
    conn = Friendship.connection(request.user, target)
    if conn:
        messages.info(request, f'You already have a connection with {target.username}.')
    else:
        Friendship.objects.create(from_user=request.user, to_user=target)
        messages.success(request, f'Friend request sent to {target.username}.')
    return redirect('friends')


@login_required
def friend_accept(request, friendship_id):
    if request.method != 'POST':
        return redirect('friends')
    fr = get_object_or_404(Friendship, pk=friendship_id, to_user=request.user, status=Friendship.STATUS_PENDING)
    fr.status = Friendship.STATUS_ACCEPTED
    fr.save()
    messages.success(request, f'You and {fr.from_user.username} are friends now.')
    return redirect('friends')


@login_required
def friend_decline(request, friendship_id):
    if request.method != 'POST':
        return redirect('friends')
    fr = get_object_or_404(Friendship, pk=friendship_id, to_user=request.user)
    fr.status = Friendship.STATUS_DECLINED
    fr.save()
    messages.info(request, f'Request from {fr.from_user.username} declined.')
    return redirect('friends')


@login_required
def friend_remove(request, friend_id):
    if request.method != 'POST':
        return redirect('friends')
    target = get_object_or_404(User, pk=friend_id)
    Friendship.connection(request.user, target).delete()
    messages.info(request, f'{target.username} removed from your friends.')
    return redirect('friends')