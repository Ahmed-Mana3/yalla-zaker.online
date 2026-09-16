"""Test-only settings: point Django at a disposable SQLite database so the
real db.sqlite3 (and the user's data) is never touched by test scripts."""
from .settings import *  # noqa: F401,F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'test_db.sqlite3',
    }
}