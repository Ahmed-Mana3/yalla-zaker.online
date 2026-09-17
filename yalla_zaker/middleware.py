import sys
import traceback

from django.http import HttpResponse
from django.http import Http404
from django.utils.html import escape


class ExceptionDebugMiddleware:
    """Catch unhandled exceptions and return formatted diagnostic details in production.

    View/resolver exceptions are converted to 500 responses below the middleware
    chain by Django, so `__call__` alone would never see them; Django's
    `process_exception` hook is what actually receives them.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except Exception:
            return self._render(request)

    def process_exception(self, request, exception):
        if isinstance(exception, Http404):
            return None
        return self._render(request)

    def _render(self, request):
        tb = traceback.format_exc()
        sys.stderr.write(
            "ExceptionDebugMiddleware caught an error while processing "
            f"{request.method} {request.get_full_path()}:\n{tb}"
        )
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Server Error (500) - Diagnostic</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace; background: #0f172a; color: #f8fafc; padding: 2rem; margin: 0;">
    <div style="max-width: 900px; margin: 0 auto;">
        <div style="background: #dc2626; color: white; padding: 1rem 1.5rem; border-radius: 8px; margin-bottom: 1.5rem;">
            <h1 style="margin: 0; font-size: 1.5rem;">Server Error (500) - Diagnostic Details</h1>
        </div>
        <p style="color: #94a3b8; font-size: 1rem;">An unhandled error occurred during request processing:</p>
        <pre style="background: #1e293b; color: #38bdf8; border: 1px solid #334155; padding: 1.25rem; border-radius: 8px; font-size: 0.9rem; line-height: 1.6; overflow-x: auto; white-space: pre-wrap;">{escape(tb)}</pre>
    </div>
</body>
</html>"""
        return HttpResponse(html, status=500, content_type="text/html")
