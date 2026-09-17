"""
WSGI config for yalla_zaker project.
"""

import html
import os
import sys
import traceback

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'yalla_zaker.settings')

_startup_error = None
_django_app = None

try:
    from django.core.wsgi import get_wsgi_application
    _django_app = get_wsgi_application()
except Exception:
    _startup_error = traceback.format_exc()
    sys.stderr.write("FATAL: yalla_zaker failed to start:\n" + _startup_error)


def application(environ, start_response):
    if _startup_error:
        body = f"""<!DOCTYPE html>
<html>
<head><title>500 Startup Error</title></head>
<body style="font-family: monospace; background: #0f172a; color: #f8fafc; padding: 2rem;">
  <div style="background: #dc2626; color: white; padding: 1rem; border-radius: 8px; margin-bottom: 1rem;">
    <h1>500 - Application Startup Error</h1>
  </div>
  <p>Django failed to initialize during WSGI startup:</p>
  <pre style="background: #1e293b; color: #38bdf8; padding: 1rem; border-radius: 8px; white-space: pre-wrap;">{html.escape(_startup_error)}</pre>
</body>
</html>""".encode("utf-8")
        start_response("500 Internal Server Error", [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ])
        return [body]

    try:
        return _django_app(environ, start_response)
    except Exception:
        tb = traceback.format_exc()
        sys.stderr.write("FATAL: Uncaught WSGI exception:\n" + tb)
        body = f"""<!DOCTYPE html>
<html>
<head><title>500 WSGI Error</title></head>
<body style="font-family: monospace; background: #0f172a; color: #f8fafc; padding: 2rem;">
  <div style="background: #dc2626; color: white; padding: 1rem; border-radius: 8px; margin-bottom: 1rem;">
    <h1>500 - Uncaught WSGI Exception</h1>
  </div>
  <pre style="background: #1e293b; color: #38bdf8; padding: 1rem; border-radius: 8px; white-space: pre-wrap;">{html.escape(tb)}</pre>
</body>
</html>""".encode("utf-8")
        start_response("500 Internal Server Error", [
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ])
        return [body]


app = application
