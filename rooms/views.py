from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import services
from .forms import GoalForm, RoomForm
from .models import Room, RoomBan, RoomMember

User = get_user_model()

BLOCK_MESSAGES = {
    Room.BLOCK_BANNED: 'You can’t join this room.',
    Room.BLOCK_LOCKED: 'The host has locked this room, so it isn’t taking new people right now.',
    Room.BLOCK_FULL: 'This room is full. Ask the host to open another seat.',
    Room.BLOCK_NOT_FRIEND: 'This room is for the host’s friends. Send them a friend request, then use this link again.',
    Room.BLOCK_NOT_IN_CHALLENGE: 'This room is only for members of its challenge. Join the challenge first, then come back.',
    Room.BLOCK_NOT_IN_AUDIENCE: 'This room is for the host’s friends and members of its challenge. Become friends with the host or join the challenge, then use this link again.',
    Room.BLOCK_LINK_ONLY: 'This room is shared by private link only.',
}


def _owned_room(request, pk):
    return get_object_or_404(Room, pk=pk, owner=request.user)


def _member_room(request, pk):
    """A room the user belongs to. Strangers get a 404 so private rooms stay invisible."""
    room = get_object_or_404(Room.objects.select_related('owner', 'challenge'), pk=pk)
    if not room.is_member(request.user):
        raise Http404
    return room


def _invite_url(request, room):
    return request.build_absolute_uri(reverse('room_invite', kwargs={'token': room.invite_token}))


def _card(room, viewer):
    rows = services.member_rows(room, viewer)
    return {'room': room, **services.summarize(rows), 'faces': [r['user'] for r in rows[:4]]}


@login_required
def room_index(request):
    mine = [_card(r, request.user) for r in Room.for_member(request.user)[:30]]
    discover = [_card(r, request.user) for r in Room.discoverable_for(request.user)[:12]]
    return render(request, 'rooms/index.html', {'mine': mine, 'discover': discover})


@login_required
def room_create(request):
    form = RoomForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        room = form.save(commit=False)
        room.owner = request.user
        room.save()
        RoomMember.objects.create(room=room, user=request.user)
        messages.success(request, 'Room is open. Share the link and start a session together.')
        return redirect('room_detail', pk=room.pk)
    return render(request, 'rooms/form.html', {'form': form, 'editing': False})


@login_required
def room_edit(request, pk):
    room = _owned_room(request, pk)
    form = RoomForm(request.POST or None, instance=room, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Room updated.')
        return redirect('room_detail', pk=room.pk)
    return render(request, 'rooms/form.html', {'form': form, 'editing': True, 'room': room})


@login_required
def room_delete(request, pk):
    room = _owned_room(request, pk)
    if request.method == 'POST':
        name = room.name
        room.delete()
        messages.info(request, f'“{name}” was closed for good.')
        return redirect('rooms')
    return render(request, 'rooms/confirm_delete.html', {'room': room})


@login_required
def room_detail(request, pk):
    room = get_object_or_404(Room.objects.select_related('owner', 'challenge'), pk=pk)
    if not room.is_member(request.user):
        # Friends / challenge rooms may be opened from the lists; a private-link
        # room must look like it does not exist unless you hold its link.
        if room.visibility != Room.VIS_LINK and room.join_block(request.user) is None:
            return redirect('room_invite', token=room.invite_token)
        raise Http404

    range_key = services.normalize_range(request.GET.get('range'))
    rows = services.member_rows(room, request.user, range_key)
    me = next(r for r in rows if r['is_me'])
    is_owner = room.owner_id == request.user.pk
    ctx = {
        'room': room,
        'rows': rows,
        'summary': services.summarize(rows),
        'range_key': range_key,
        'ranges': services.RANGES,
        'me': me,
        'is_owner': is_owner,
        'invite_url': _invite_url(request, room),
        'goal_form': GoalForm(initial={'goal': me['goal']}),
        'banned': room.banned.select_related('user') if is_owner else [],
    }
    return render(request, 'rooms/detail.html', ctx)


@login_required
def room_state_api(request, pk):
    """Polled by the room page so presence stays live without reloads."""
    room = _member_room(request, pk)
    range_key = services.normalize_range(request.GET.get('range'))
    rows = services.member_rows(room, request.user, range_key)
    return JsonResponse({
        'summary': services.summarize(rows),
        'rows': [services.row_to_json(r) for r in rows],
    })


def room_invite(request, token):
    """The landing page behind a shared link. Works logged out so the invite is never a dead end."""
    room = get_object_or_404(Room.objects.select_related('owner', 'challenge'), invite_token=token)
    block = None
    if request.user.is_authenticated:
        if room.is_member(request.user):
            return redirect('room_detail', pk=room.pk)
        block = room.join_block(request.user, via_link=True)
    rows = services.member_rows(room, request.user if request.user.is_authenticated else room.owner)
    ctx = {
        'room': room,
        'block': block,
        'block_message': BLOCK_MESSAGES.get(block, ''),
        'summary': services.summarize(rows),
        'faces': [r['user'] for r in rows[:5]],
        'next_url': request.get_full_path(),
    }
    return render(request, 'rooms/invite.html', ctx)


@login_required
@require_POST
def room_join(request, token):
    with transaction.atomic():
        room = get_object_or_404(Room.objects.select_for_update(), invite_token=token)
        if room.is_member(request.user):
            return redirect('room_detail', pk=room.pk)
        block = room.join_block(request.user, via_link=True)
        if block:
            messages.warning(request, BLOCK_MESSAGES[block])
            return redirect('room_invite', token=token)
        RoomMember.objects.get_or_create(room=room, user=request.user)
    messages.success(request, f'You’re in — {room.name}.')
    return redirect('room_detail', pk=room.pk)


@login_required
@require_POST
def room_join_code(request):
    """Accepts a pasted invite link or a bare code and sends the user to its landing page."""
    raw = (request.POST.get('code') or '').strip()
    token = raw.rstrip('/').rsplit('/', 1)[-1].split('?')[0] if raw else ''
    if token and Room.objects.filter(invite_token=token).exists():
        return redirect('room_invite', token=token)
    messages.warning(request, 'That link doesn’t match any room. Check it with whoever sent it.')
    return redirect('rooms')


@login_required
@require_POST
def room_leave(request, pk):
    room = _member_room(request, pk)
    if room.owner_id == request.user.pk:
        messages.warning(request, 'You host this room, so you can’t leave it. Delete the room instead.')
        return redirect('room_detail', pk=pk)
    room.members.filter(user=request.user).delete()
    messages.info(request, f'You left “{room.name}”.')
    return redirect('rooms')


@login_required
@require_POST
def room_goal(request, pk):
    room = _member_room(request, pk)
    form = GoalForm(request.POST)
    if form.is_valid():
        room.members.filter(user=request.user).update(goal=form.cleaned_data['goal'].strip())
    if request.headers.get('x-requested-with') == 'fetch':
        return JsonResponse({'ok': form.is_valid()})
    messages.success(request, 'Status updated.')
    return redirect('room_detail', pk=pk)


@login_required
@require_POST
def room_regenerate_invite(request, pk):
    room = _owned_room(request, pk)
    room.regenerate_invite()
    messages.success(request, 'New link created. The old one no longer works.')
    return redirect('room_detail', pk=pk)


@login_required
@require_POST
def room_toggle_lock(request, pk):
    room = _owned_room(request, pk)
    room.is_locked = not room.is_locked
    room.save(update_fields=['is_locked'])
    messages.info(request, 'Room locked — no new people can join.' if room.is_locked else 'Room unlocked.')
    return redirect('room_detail', pk=pk)


@login_required
@require_POST
def room_kick(request, pk, user_id):
    room = _owned_room(request, pk)
    target = get_object_or_404(User, pk=user_id)
    if target.pk == room.owner_id:
        messages.warning(request, 'You can’t remove yourself from your own room.')
        return redirect('room_detail', pk=pk)
    room.members.filter(user=target).delete()
    RoomBan.objects.get_or_create(room=room, user=target)
    messages.info(request, f'{target.username} was removed and can’t rejoin unless you allow them back.')
    return redirect('room_detail', pk=pk)


@login_required
@require_POST
def room_unban(request, pk, user_id):
    room = _owned_room(request, pk)
    room.banned.filter(user_id=user_id).delete()
    messages.success(request, 'They can use the room link again.')
    return redirect('room_detail', pk=pk)
