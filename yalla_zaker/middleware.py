import os
import sys
import traceback

from django.core.signals import got_request_exception
from django.dispatch import receiver
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.utils.html import escape


@receiver(got_request_exception)
def capture_request_exception(sender, request, **kwargs):
    """Capture exception traceback for any request exception across all middlewares."""
    if request is not None:
        request._captured_exception_traceback = traceback.format_exc()


def _request_diagnostics(request):
    method = getattr(request, "method", "UNKNOWN")
    try:
        path = request.get_full_path()
    except Exception:
        path = getattr(request, "path", "UNKNOWN")
    try:
        host = request.get_host()
    except Exception:
        host = getattr(request, "META", {}).get("HTTP_HOST", "UNKNOWN")

    db_configured = bool(os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL_NON_POOLING") or os.environ.get("POSTGRES_URL"))

    return {
        "method": method,
        "path": path,
        "host": host,
        "db_configured": db_configured,
        "python_version": sys.version.split()[0],
    }


def _plain_error_page(request, status, headline, message, requested_path=None):
    """Last-resort themed error page for when the template layer itself is unavailable."""
    if not requested_path:
        try:
            requested_path = request.get_full_path()
        except Exception:
            requested_path = getattr(request, "path", "")

    danger = {"500", "503", "502"}
    amber = "#E2574C" if str(status) in danger else "#F5A524"
    glow = "rgba(226, 87, 76, 0.28)" if str(status) in danger else "rgba(245, 165, 36, 0.35)"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>{status} - {escape(headline)}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500;600;700&display=swap" rel="stylesheet">
</head>
<body style="margin:0;min-height:100vh;background:#0E1218;color:#E9EDF3;font-family:Inter,-apple-system,'Segoe UI',system-ui,sans-serif;display:flex;align-items:center;justify-content:center;">
    <div style="text-align:center;max-width:560px;padding:48px 22px;display:flex;flex-direction:column;align-items:center;">
        <div style="width:92px;height:92px;border-radius:50%;background:radial-gradient(circle at 50% 42%,#202A39,#161C26 60%,#0E1218 130%);border:1px solid #34405A;display:grid;place-items:center;color:{amber};box-shadow:0 0 46px {glow};margin-bottom:22px;font-family:'JetBrains Mono',monospace;font-size:1.6rem;font-weight:700;">{status}</div>
        <p style="margin:0 0 10px;font-size:0.72rem;letter-spacing:0.16em;text-transform:uppercase;color:#647084;font-family:'Space Grotesk',sans-serif;font-weight:600;">yalla zaker — the night desk</p>
        <h1 style="margin:0 0 10px;font-family:'Space Grotesk',sans-serif;font-size:clamp(1.6rem,4vw,2.2rem);letter-spacing:-0.02em;">{escape(headline)}</h1>
        <p style="margin:0;color:#93A0B2;line-height:1.6;">{escape(message)}</p>
        <code style="margin-top:22px;font-size:0.82rem;color:#93A0B2;background:#1B2330;border:1px solid #273040;border-radius:999px;padding:7px 15px;font-family:'JetBrains Mono',monospace;">{escape(requested_path)}</code>
        <div style="margin-top:26px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
            <a href="/" style="display:inline-flex;align-items:center;padding:11px 18px;border-radius:10px;background:#F5A524;color:#171107;font-weight:600;text-decoration:none;font-size:0.92rem;box-shadow:0 6px 20px rgba(245,165,36,0.35);">Back to home</a>
        </div>
    </div>
</body>
</html>"""
    return HttpResponse(html, status=status, content_type="text/html")


def render_page_or_fallback(request, template, context, status):
    """Render an error template, or return an inline page if rendering fails."""
    try:
        response = render(request, template, context, status=status)
        if hasattr(response, "render"):
            response.render()
        return response
    except Exception:
        tb = context.get("tb")
        if status == 500:
            return render_diagnostic(request, tb=tb, status=500)
        return _plain_error_page(
            request,
            status,
            context.get("headline", f"Error ({status})"),
            context.get("message", "Something went wrong."),
        )


def render_diagnostic(request, tb=None, status=500):
    """Fallback plain-HTML diagnostic used when the template layer itself is broken.

    Renders the same on-brand error page as templates/errors/500.html, with the
    traceback tucked behind a <details> toggle so production data isn't lost.
    """
    if not tb:
        tb = getattr(request, "_captured_exception_traceback", None) or traceback.format_exc()
    if not tb or tb.strip() == "NoneType: None":
        tb = "No Python traceback available (error occurred outside exception frame or in pre-middleware stack)."

    diag = _request_diagnostics(request)
    sys.stderr.write(
        f"Diagnostic caught status {status} while processing {diag['method']} {diag['path']} (host: {diag['host']}):\n{tb}\n"
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>500 - The lamp flickered</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500;600;700&display=swap" rel="stylesheet">
</head>
<body style="margin:0;min-height:100vh;background:
    radial-gradient(1000px 500px at 85% -10%, rgba(255,180,60,0.05), transparent 60%),
    radial-gradient(900px 700px at -10% 110%, rgba(60,90,180,0.07), transparent 60%),
    #0E1218;color:#E9EDF3;font-family:Inter,-apple-system,'Segoe UI',system-ui,sans-serif;display:flex;align-items:center;justify-content:center;">
    <div style="text-align:center;max-width:600px;padding:48px 22px;display:flex;flex-direction:column;align-items:center;">
        <div style="width:92px;height:92px;border-radius:50%;background:radial-gradient(circle at 50% 42%,#202A39,#161C26 60%,#0E1218 130%);border:1px solid #34405A;display:grid;place-items:center;color:#E2574C;box-shadow:0 0 46px rgba(226,87,76,0.28);margin-bottom:22px;font-family:'JetBrains Mono',monospace;font-size:1.6rem;font-weight:700;animation:flash 1.6s ease-in-out infinite;">500</div>
        <p style="margin:0 0 10px;font-size:0.72rem;letter-spacing:0.16em;text-transform:uppercase;color:#647084;font-family:'Space Grotesk',sans-serif;font-weight:600;">yalla zaker — the night desk</p>
        <h1 style="margin:0 0 10px;font-family:'Space Grotesk',sans-serif;font-size:clamp(1.6rem,4vw,2.2rem);letter-spacing:-0.02em;">The lamp flickered.</h1>
        <p style="margin:0;color:#93A0B2;line-height:1.6;max-width:440px;">Something on our side glitched while loading this page. Try again in a moment — we've logged the fault.</p>
        <details style="margin-top:34px;width:100%;text-align:left;background:#161C26;border:1px solid #273040;border-radius:9px;overflow:hidden;">
            <summary style="cursor:pointer;padding:12px 16px;color:#93A0B2;font-size:0.82rem;font-weight:500;list-style:none;">Technical details</summary>
            <dl style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 18px;margin:0;padding:14px 16px;">
                <div><dt style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;color:#647084;font-weight:600;margin-bottom:2px;">Request</dt><dd style="margin:0;font-size:0.84rem;color:#93A0B2;word-break:break-all;">{escape(str(diag['method']))} {escape(str(diag['path']))}</dd></div>
                <div><dt style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;color:#647084;font-weight:600;margin-bottom:2px;">Host</dt><dd style="margin:0;font-size:0.84rem;color:#93A0B2;word-break:break-all;">{escape(str(diag['host']))}</dd></div>
                <div><dt style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;color:#647084;font-weight:600;margin-bottom:2px;">Database env</dt><dd style="margin:0;font-size:0.84rem;color:#93A0B2;">{"present" if diag["db_configured"] else "missing"}</dd></div>
                <div><dt style="font-size:0.68rem;text-transform:uppercase;letter-spacing:0.1em;color:#647084;font-weight:600;margin-bottom:2px;">Python</dt><dd style="margin:0;font-size:0.84rem;color:#93A0B2;font-family:'JetBrains Mono',monospace;">{escape(diag['python_version'])}</dd></div>
            </dl>
            <pre style="max-height:320px;overflow:auto;margin:0;padding:14px 16px;background:#0B0F14;border-top:1px solid #273040;color:#9FB4E8;font-size:0.78rem;line-height:1.55;white-space:pre-wrap;border-radius:0 0 9px 9px;">{escape(tb)}</pre>
        </details>
        <div style="margin-top:26px;display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
            <a href="/" style="display:inline-flex;align-items:center;padding:11px 18px;border-radius:10px;background:#F5A524;color:#171107;font-weight:600;text-decoration:none;font-size:0.92rem;box-shadow:0 6px 20px rgba(245,165,36,0.35);">Back to home</a>
        </div>
    </div>
    <style>@keyframes flash{{0%,100%{{box-shadow:0 0 18px rgba(226,87,76,0.15);}}50%{{box-shadow:0 0 46px rgba(226,87,76,0.38);}}}}</style>
</body>
</html>"""
    return HttpResponse(html, status=status, content_type="text/html")


def server_error(request):
    """Custom handler500 view that returns a styled diagnostic page."""
    tb = getattr(request, "_captured_exception_traceback", None) or traceback.format_exc()
    return render_page_or_fallback(
        request,
        "errors/500.html",
        {
            "tb": tb,
            "diag": _request_diagnostics(request),
            "error_code": "500",
            "headline": "The lamp flickered.",
            "message": "Something on our side glitched while loading this page. Try again in a moment — we've logged the fault.",
            "lamp_state": "is-red",
        },
        status=500,
    )


def page_not_found(request, exception=None):
    """Custom handler404 view that safely handles missing 404 templates."""
    path = getattr(request, "path", "")
    return render_page_or_fallback(
        request,
        "errors/404.html",
        {
            "requested_path": path,
            "error_code": "404",
            "headline": "No desk at this address.",
            "message": "The page you're looking for isn't here — a wrong path, a shelf that moved, or a link that fizzled out. Your study streak is unaffected.",
            "lamp_state": "is-cold",
        },
        status=404,
    )


def permission_denied(request, exception=None):
    """Custom handler403 view."""
    path = getattr(request, "path", "")
    return render_page_or_fallback(
        request,
        "errors/403.html",
        {
            "requested_path": path,
            "error_code": "403",
            "headline": "This desk is for members only.",
            "message": "You don't hold the key for this one. If you think you should, find the owner and ask nicely.",
            "lamp_state": "is-cold",
        },
        status=403,
    )


def bad_request(request, exception=None):
    """Custom handler400 view."""
    path = getattr(request, "path", "")
    return render_page_or_fallback(
        request,
        "errors/400.html",
        {
            "requested_path": path,
            "error_code": "400",
            "headline": "That request doesn't parse.",
            "message": "The browser sent something we couldn't read. Go back and try again — no real harm done.",
            "lamp_state": "is-cold",
        },
        status=400,
    )


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
        return response

    def process_exception(self, request, exception):
        if isinstance(exception, Http404):
            return None
        tb = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))
        request._captured_exception_traceback = tb
        return render_diagnostic(request, tb=tb)