from .models import Friendship


def friend_requests(request):
    """Count of friend requests the user hasn't seen yet, for the nav badge."""
    if not request.user.is_authenticated:
        return {}
    return {'unseen_friend_requests': Friendship.unseen_requests_for(request.user).count()}
