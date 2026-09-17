import os
import sys
import traceback

from django.core.signals import got_request_exception
from django.dispatch import receiver
from django.http import Http404, HttpResponse
from django.utils.html import escape


@receiver(got_request_exception)
def capture_request_exception(sender, request, **kwargs):
    """Capture exception traceback for any request exception across all middlewares."""
    if request is not None:
        request._captured_exception_traceback = traceback.format_exc()


def render_diagnostic(request, tb=None, status=500):
    if not tb:
        tb = getattr(request, "_captured_exception_traceback", None) or traceback.format_exc()
    if not tb or tb.strip() == "NoneType: None":
        tb = "No Python traceback available (error occurred outside exception frame or in pre-middleware stack)."

    method = getattr(request, "method", "UNKNOWN")
    try:
        path = request.get_full_path()
    except Exception:
        path = getattr(request, "path", "UNKNOWN")
    try:
        host = request.get_host()
    except Exception:
        host = getattr(request, "META", {}).get("HTTP_HOST", "UNKNOWN")

    sys.stderr.write(
        f"Diagnostic caught status {status} while processing {method} {path} (host: {host}):\n{tb}\n"
    )

    db_configured = bool(os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL_NON_POOLING") or os.environ.get("POSTGRES_URL"))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Server Error ({status}) - Diagnostic</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace; background: #0f172a; color: #f8fafc; padding: 2rem; margin: 0;">
    <div style="max-width: 960px; margin: 0 auto;">
        <div style="background: #dc2626; color: white; padding: 1rem 1.5rem; border-radius: 8px; margin-bottom: 1.5rem;">
            <h1 style="margin: 0; font-size: 1.5rem;">Server Error ({status}) - Diagnostic Details</h1>
        </div>
        <div style="background: #1e293b; border: 1px solid #334155; padding: 1rem 1.25rem; border-radius: 8px; margin-bottom: 1.5rem; font-size: 0.9rem; line-height: 1.7;">
            <div><strong>Request:</strong> <code>{escape(method)} {escape(path)}</code></div>
            <div><strong>Host:</strong> <code>{escape(str(host))}</code></div>
            <div><strong>Database Env Present:</strong> <code>{db_configured}</code></div>
            <div><strong>Python:</strong> <code>{escape(sys.version.split()[0])}</code></div>
        </div>
        <p style="color: #94a3b8; font-size: 1rem;">Traceback / Error Details:</p>
        <pre style="background: #1e293b; color: #38bdf8; border: 1px solid #334155; padding: 1.25rem; border-radius: 8px; font-size: 0.88rem; line-height: 1.6; overflow-x: auto; white-space: pre-wrap;">{escape(tb)}</pre>
    </div>
</body>
</html>"""
    return HttpResponse(html, status=status, content_type="text/html")


def server_error(request):
    """Custom handler500 view that returns detailed diagnostic information."""
    return render_diagnostic(request, status=500)


def page_not_found(request, exception=None):
    """Custom handler404 view that safely handles missing 404 templates."""
    path = getattr(request, "path", "")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Page Not Found (404)</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace; background: #0f172a; color: #f8fafc; padding: 2rem; margin: 0; text-align: center;">
    <h1 style="color: #f59e0b; margin-top: 4rem;">404 — Page Not Found</h1>
    <p style="color: #94a3b8;">The requested URL <code>{escape(path)}</code> was not found on this server.</p>
    <p><a href="/" style="color: #38bdf8;">Return to Home</a></p>
</body>
</html>"""
    return HttpResponse(html, status=404, content_type="text/html")


class ExceptionDebugMiddleware:
    """Catch unhandled exceptions and return formatted diagnostic details in production."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
        except Exception as exc:
            tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
            return render_diagnostic(request, tb=tb)

        if response.status_code == 500:
            tb = getattr(request, "_captured_exception_traceback", None)
            if tb:
                return render_diagnostic(request, tb=tb)
        return response

    def process_exception(self, request, exception):
        if isinstance(exception, Http404):
            return None
        tb = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        request._captured_exception_traceback = tb
        return render_diagnostic(request, tb=tb)
