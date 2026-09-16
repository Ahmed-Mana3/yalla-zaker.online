import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get(
    "SECRET_KEY",
    "django-insecure-ypa2zca3xjwssii-m&o9uujufu%g%2=(8gwh*z4ugwrwx$rp7p",
)

DEBUG = os.environ.get("DEBUG", "True").lower() in ("true", "1", "yes")

# Allowed Hosts
raw_allowed_hosts = os.environ.get("ALLOWED_HOSTS")
if raw_allowed_hosts:
    ALLOWED_HOSTS = [h.strip() for h in raw_allowed_hosts.split(",") if h.strip()]
else:
    ALLOWED_HOSTS = [
        "yalla-zaker.onine",
        "www.yalla-zaker.onine",
        ".yalla-zaker.onine",
        "yalla-zaker.online",
        "www.yalla-zaker.online",
        ".yalla-zaker.online",
        ".vercel.app",
        "localhost",
        "127.0.0.1",
    ]

# CSRF Trusted Origins (required for HTTPS POST requests on production)
CSRF_TRUSTED_ORIGINS = [
    "https://yalla-zaker.onine",
    "https://www.yalla-zaker.onine",
    "https://*.yalla-zaker.onine",
    "https://yalla-zaker.online",
    "https://www.yalla-zaker.online",
    "https://*.yalla-zaker.online",
    "https://*.vercel.app",
]
raw_csrf = os.environ.get("CSRF_TRUSTED_ORIGINS")
if raw_csrf:
    CSRF_TRUSTED_ORIGINS.extend([origin.strip() for origin in raw_csrf.split(",") if origin.strip()])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "courses",
    "studysessions",
    "challenges",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.OnlineStatusMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "yalla_zaker.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "yalla_zaker.context_processors.seo",
            ],
        },
    },
]

WSGI_APPLICATION = "yalla_zaker.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=int(os.environ.get("CONN_MAX_AGE", "0")),
        ssl_require="DATABASE_URL" in os.environ,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "home"

# A running session may be paused for at most this many minutes before it ends.
MAX_BREAK_MINUTES = 30

# Presence: a user counts as "online" if active on the site within this window.
ONLINE_WINDOW_MINUTES = 5

# OnlineStatusMiddleware writes Profile.last_seen at most this often per session.
ONLINE_THROTTLE_SECONDS = 60

# SEO: pin the production domain here so sitemap/robots/canonical use it.
# Left empty, the request's own host is used (works in dev and on any host).
SEO_CANONICAL_HOST = os.environ.get("SEO_CANONICAL_HOST", "")

# Production security settings (only when DEBUG is off)
if not DEBUG:
    SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "True").lower() in ("true", "1", "yes")
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = "DENY"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{levelname}] {asctime} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}
