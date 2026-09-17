"""
WSGI config for yalla_zaker project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/howto/deployment/wsgi/
"""

import os
import sys
import traceback

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yalla_zaker.settings')

try:
    application = get_wsgi_application()
except Exception:
    # Vercel swallows import failures into a bare 500; print the real cause to
    # the function logs so it shows up under Deployments -> Runtime Logs.
    sys.stderr.write("FATAL: yalla_zaker failed to start:\n" + traceback.format_exc())
    raise

app = application
