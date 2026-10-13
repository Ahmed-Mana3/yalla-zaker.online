from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ChallengeForm
from .models import Challenge, ChallengeMember


FACES_SHOWN = 5


def challenge_index(request):
    today = timezone.now().date()
    challenges = list(Challenge.objects.prefetch_related('members__user__profile'))
    mine = set()
    if request.user.is_authenticated:
        mine = set(ChallengeMember.objects.filter(user=request.user).values_list('challenge_id', flat=True))

    # card extras: who's in, how far along the window is, and whether I joined
    for c in challenges:
        people = [m.user for m in c.members.all()]
        c.member_count = len(people)
        c.faces = people[:FACES_SHOWN]
        c.more_faces = max(len(people) - FACES_SHOWN, 0)
        c.joined = c.pk in mine
        c.days_total = max((c.ends_at - c.starts_at).days + 1, 1)
        c.day_num = min(max((today - c.starts_at).days + 1, 0), c.days_total)
        c.days_left = (c.ends_at - today).days
        c.starts_in = (c.starts_at - today).days
        c.pct = round(100 * c.day_num / c.days_total)

    active = sorted((c for c in challenges if c.starts_at <= today <= c.ends_at), key=lambda c: c.days_left)
    upcoming = sorted((c for c in challenges if c.starts_at > today), key=lambda c: c.starts_at)
    past = sorted((c for c in challenges if c.ends_at < today), key=lambda c: c.ends_at, reverse=True)
    ctx = {
        'active': active,
        'upcoming': upcoming,
        'past': past,
        'racing': len({m.user_id for c in active for m in c.members.all()}),
        'joined_count': sum(1 for c in active + upcoming if c.joined),
    }
    return render(request, 'challenges/index.html', ctx)


@login_required
def challenge_create(request):
    form = ChallengeForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        challenge = form.save(commit=False)
        challenge.created_by = request.user
        challenge.save()
        ChallengeMember.objects.create(challenge=challenge, user=request.user)
        messages.success(request, 'Challenge up. Who is winning?')
        return redirect('challenge_detail', pk=challenge.pk)
    return render(request, 'challenges/form.html', {'form': form})


def challenge_detail(request, pk):
    challenge = get_object_or_404(Challenge, pk=pk)
    is_member = request.user.is_authenticated and challenge.members.filter(user=request.user).exists()
    leaderboard = ChallengeMember.leaderboard(challenge)
    me = None
    if is_member:
        sh = ChallengeMember.member_stats(request.user, challenge)
        me = sh
    ctx = {
        'challenge': challenge,
        'is_member': is_member,
        'leaderboard': leaderboard,
        'me': me,
        'now': timezone.now().date(),
    }
    return render(request, 'challenges/detail.html', ctx)


@login_required
def challenge_join(request, pk):
    if request.method != 'POST':
        return redirect('challenge_detail', pk=pk)
    challenge = get_object_or_404(Challenge, pk=pk)
    member, created = ChallengeMember.objects.get_or_create(challenge=challenge, user=request.user)
    if created:
        messages.success(request, f'You’re in — {challenge.title}.')
    else:
        messages.info(request, 'Already in this one.')
    return redirect('challenge_detail', pk=pk)