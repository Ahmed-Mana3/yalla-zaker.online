import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import Friendship
from challenges.models import Challenge, ChallengeMember
from studysessions.models import StudySegment, StudySession

from .models import Room, RoomBan, RoomMember

User = get_user_model()


def make_user(name):
    return User.objects.create_user(name, f'{name}@example.com', 'pw-12345-xyz')


def befriend(a, b):
    Friendship.objects.create(from_user=a, to_user=b, status=Friendship.STATUS_ACCEPTED)


def make_room(owner, **kwargs):
    kwargs.setdefault('name', 'Night shift')
    room = Room.objects.create(owner=owner, **kwargs)
    RoomMember.objects.create(room=room, user=owner)
    return room


class RoomAccessTests(TestCase):
    def setUp(self):
        self.host = make_user('host')
        self.pal = make_user('pal')
        self.stranger = make_user('stranger')
        befriend(self.host, self.pal)

    def test_friends_room_visible_to_friends_only(self):
        room = make_room(self.host, visibility=Room.VIS_FRIENDS)
        self.assertIn(room, Room.discoverable_for(self.pal))
        self.assertNotIn(room, Room.discoverable_for(self.stranger))
        self.assertIsNone(room.join_block(self.pal))
        self.assertEqual(room.join_block(self.stranger, via_link=True), Room.BLOCK_NOT_FRIEND)

    def test_challenge_room_visible_to_challenge_members(self):
        today = timezone.localdate()
        ch = Challenge.objects.create(title='Finals', created_by=self.host, starts_at=today,
                                      ends_at=today + dt.timedelta(days=7))
        ChallengeMember.objects.create(challenge=ch, user=self.host)
        ChallengeMember.objects.create(challenge=ch, user=self.stranger)
        room = make_room(self.host, visibility=Room.VIS_CHALLENGE, challenge=ch)
        self.assertIn(room, Room.discoverable_for(self.stranger))
        self.assertNotIn(room, Room.discoverable_for(self.pal))  # friend, but not in the challenge
        self.assertEqual(room.join_block(self.pal, via_link=True), Room.BLOCK_NOT_IN_CHALLENGE)

    def test_both_room_opens_to_friends_and_challenge_members_but_not_others(self):
        today = timezone.localdate()
        ch = Challenge.objects.create(title='Finals', created_by=self.host, starts_at=today,
                                      ends_at=today + dt.timedelta(days=7))
        ChallengeMember.objects.create(challenge=ch, user=self.host)
        mate = make_user('mate')
        ChallengeMember.objects.create(challenge=ch, user=mate)
        room = make_room(self.host, visibility=Room.VIS_BOTH, challenge=ch)
        self.assertIn(room, Room.discoverable_for(self.pal))      # friend only
        self.assertIn(room, Room.discoverable_for(mate))          # challenge member only
        self.assertNotIn(room, Room.discoverable_for(self.stranger))
        self.assertEqual(room.join_block(self.stranger, via_link=True), Room.BLOCK_NOT_IN_AUDIENCE)
        self.assertIn('friends', room.audience_label)
        self.assertIn('Finals', room.audience_label)

    def test_link_room_is_never_listed_and_needs_the_link(self):
        room = make_room(self.host, visibility=Room.VIS_LINK)
        self.assertNotIn(room, Room.discoverable_for(self.pal))
        self.assertEqual(room.join_block(self.pal), Room.BLOCK_LINK_ONLY)
        self.assertIsNone(room.join_block(self.stranger, via_link=True))

    def test_full_locked_and_banned(self):
        room = make_room(self.host, visibility=Room.VIS_LINK, capacity=2)
        RoomMember.objects.create(room=room, user=self.pal)
        self.assertEqual(room.join_block(self.stranger, via_link=True), Room.BLOCK_FULL)
        room.capacity = 5
        room.is_locked = True
        self.assertEqual(room.join_block(self.stranger, via_link=True), Room.BLOCK_LOCKED)
        room.is_locked = False
        RoomBan.objects.create(room=room, user=self.stranger)
        self.assertEqual(room.join_block(self.stranger, via_link=True), Room.BLOCK_BANNED)


class RoomViewTests(TestCase):
    def setUp(self):
        self.host = make_user('host')
        self.pal = make_user('pal')
        self.stranger = make_user('stranger')
        befriend(self.host, self.pal)

    def test_create_room_makes_owner_a_member(self):
        self.client.force_login(self.host)
        resp = self.client.post(reverse('room_create'), {
            'name': 'Calc', 'topic': 'ch 4', 'visibility': 'link', 'capacity': 4})
        room = Room.objects.get()
        self.assertRedirects(resp, reverse('room_detail', kwargs={'pk': room.pk}))
        self.assertTrue(room.is_member(self.host))
        self.assertEqual(len(room.invite_token) >= 16, True)

    def test_challenge_visibility_requires_a_challenge(self):
        self.client.force_login(self.host)
        resp = self.client.post(reverse('room_create'), {
            'name': 'Calc', 'visibility': 'challenge', 'capacity': 4})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Room.objects.exists())
        self.assertContains(resp, 'running challenge')

    def test_index_renders_for_new_user(self):
        self.client.force_login(self.stranger)
        resp = self.client.get(reverse('rooms'))
        self.assertContains(resp, 'not in a room yet')

    def test_anonymous_invite_page_works_and_points_to_login_with_next(self):
        room = make_room(self.host, visibility=Room.VIS_LINK)
        url = reverse('room_invite', kwargs={'token': room.invite_token})
        resp = self.client.get(url)
        self.assertContains(resp, 'Log in to join')
        self.assertContains(resp, 'noindex')
        self.assertContains(resp, '?next=')

    def test_join_via_link_then_leave(self):
        room = make_room(self.host, visibility=Room.VIS_LINK)
        self.client.force_login(self.stranger)
        resp = self.client.post(reverse('room_join', kwargs={'token': room.invite_token}))
        self.assertRedirects(resp, reverse('room_detail', kwargs={'pk': room.pk}))
        self.assertTrue(room.is_member(self.stranger))
        self.client.post(reverse('room_leave', kwargs={'pk': room.pk}))
        self.assertFalse(room.is_member(self.stranger))

    def test_stranger_cannot_join_friends_room_even_with_link(self):
        room = make_room(self.host, visibility=Room.VIS_FRIENDS)
        self.client.force_login(self.stranger)
        resp = self.client.post(reverse('room_join', kwargs={'token': room.invite_token}), follow=True)
        self.assertFalse(room.is_member(self.stranger))
        self.assertContains(resp, 'friends')

    def test_friend_can_join_from_detail_redirect(self):
        room = make_room(self.host, visibility=Room.VIS_FRIENDS)
        self.client.force_login(self.pal)
        resp = self.client.get(reverse('room_detail', kwargs={'pk': room.pk}))
        self.assertRedirects(resp, reverse('room_invite', kwargs={'token': room.invite_token}))

    def test_private_room_detail_is_404_for_outsiders(self):
        room = make_room(self.host, visibility=Room.VIS_LINK)
        self.client.force_login(self.pal)
        self.assertEqual(self.client.get(reverse('room_detail', kwargs={'pk': room.pk})).status_code, 404)
        self.assertEqual(self.client.get(reverse('room_state_api', kwargs={'pk': room.pk})).status_code, 404)

    def test_owner_cannot_leave(self):
        room = make_room(self.host)
        self.client.force_login(self.host)
        self.client.post(reverse('room_leave', kwargs={'pk': room.pk}))
        self.assertTrue(room.is_member(self.host))

    def test_kick_bans_and_unban_restores(self):
        room = make_room(self.host, visibility=Room.VIS_LINK)
        RoomMember.objects.create(room=room, user=self.stranger)
        self.client.force_login(self.host)
        self.client.post(reverse('room_kick', kwargs={'pk': room.pk, 'user_id': self.stranger.pk}))
        self.assertFalse(room.is_member(self.stranger))
        self.assertIsNotNone(room.join_block(self.stranger, via_link=True))
        self.client.post(reverse('room_unban', kwargs={'pk': room.pk, 'user_id': self.stranger.pk}))
        self.assertIsNone(room.join_block(self.stranger, via_link=True))

    def test_only_owner_can_manage(self):
        room = make_room(self.host)
        RoomMember.objects.create(room=room, user=self.pal)
        self.client.force_login(self.pal)
        for name in ('room_edit', 'room_delete'):
            self.assertEqual(self.client.get(reverse(name, kwargs={'pk': room.pk})).status_code, 404)
        for name in ('room_regenerate_invite', 'room_toggle_lock'):
            self.assertEqual(self.client.post(reverse(name, kwargs={'pk': room.pk})).status_code, 404)

    def test_regenerated_link_invalidates_old_one(self):
        room = make_room(self.host, visibility=Room.VIS_LINK)
        old = room.invite_token
        self.client.force_login(self.host)
        self.client.post(reverse('room_regenerate_invite', kwargs={'pk': room.pk}))
        room.refresh_from_db()
        self.assertNotEqual(room.invite_token, old)
        self.assertEqual(self.client.get(reverse('room_invite', kwargs={'token': old})).status_code, 404)

    def test_join_code_accepts_pasted_url(self):
        room = make_room(self.host, visibility=Room.VIS_LINK)
        self.client.force_login(self.stranger)
        url = f'https://yalla-zaker.online/rooms/invite/{room.invite_token}/'
        resp = self.client.post(reverse('room_join_code'), {'code': url})
        self.assertRedirects(resp, reverse('room_invite', kwargs={'token': room.invite_token}))
        resp = self.client.post(reverse('room_join_code'), {'code': 'nope'}, follow=True)
        self.assertContains(resp, 'doesn’t match any room')

    def test_goal_update_and_detail_render(self):
        room = make_room(self.host)
        self.client.force_login(self.host)
        self.client.post(reverse('room_goal', kwargs={'pk': room.pk}), {'goal': 'Chapter 4'})
        resp = self.client.get(reverse('room_detail', kwargs={'pk': room.pk}))
        self.assertContains(resp, 'Chapter 4')
        self.assertContains(resp, 'just you for now')

    def test_signup_keeps_invite_next(self):
        room = make_room(self.host, visibility=Room.VIS_LINK)
        nxt = reverse('room_invite', kwargs={'token': room.invite_token})
        resp = self.client.post(f'{reverse("signup")}?next={nxt}', {
            'username': 'newbie', 'email': 'n@example.com',
            'password1': 'S0me-long-pass-99', 'password2': 'S0me-long-pass-99'})
        if resp.status_code == 302:
            self.assertIn('next=', resp['Location'])


class RoomPresenceTests(TestCase):
    def test_state_api_reports_live_member_and_today_time(self):
        host = make_user('host')
        pal = make_user('pal')
        room = make_room(host, visibility=Room.VIS_LINK)
        RoomMember.objects.create(room=room, user=pal)

        now = timezone.now()
        done = StudySession.objects.create(user=pal, status='finished', started_at=now - dt.timedelta(minutes=50),
                                           ended_at=now - dt.timedelta(minutes=20), duration_seconds=1800)
        StudySegment.objects.create(session=done, started_at=done.started_at, ended_at=done.ended_at)
        running = StudySession.objects.create(user=host, status='active', started_at=now - dt.timedelta(minutes=5))
        StudySegment.objects.create(session=running, started_at=running.started_at)

        self.client.force_login(host)
        data = self.client.get(reverse('room_state_api', kwargs={'pk': room.pk})).json()
        by_name = {r['username']: r for r in data['rows']}
        self.assertEqual(by_name['host']['status'], 'live')
        self.assertGreaterEqual(by_name['host']['elapsed'], 299)
        self.assertGreaterEqual(by_name['pal']['seconds'], 1790)
        self.assertEqual(by_name['pal']['status'], 'offline')
        self.assertEqual(data['summary']['studying'], 1)
        # ranking: pal studied longer today
        self.assertEqual(data['rows'][0]['username'], 'pal')
