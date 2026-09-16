from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ChallengeForm
from .models import Challenge, ChallengeMember


def challenge_index(request):
    today = timezone.now().date()
    challenges = Challenge.objects.all()
    ctx = {
        'active': [c for c in challenges if c.is_active()],
        'upcoming': [c for c in challenges if c.starts_at > today],
        'past': [c for c in challenges if c.ends_at < today],
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