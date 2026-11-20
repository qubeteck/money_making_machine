"""Serve the compiled Vite/React dashboard from /ui.

The single-page app is built into ``web/dist``.  Development runs on Vite's own
server with a proxy; this module only handles the production build.  Keeping the
fallback here means a missing build never breaks the Python app or the legacy
Jinja dashboard at ``/``.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.config import BASE_DIR

router = APIRouter(include_in_schema=False)

DIST_DIR = BASE_DIR / "web" / "dist"
INDEX_FILE = DIST_DIR / "index.html"

# Standalone systems documentation page written in web/docs.html. It is served
# publicly under /ui/docs.html so Telegram users can open it without signing in
# to the dashboard.
DOCS_FILE = BASE_DIR / "web" / "docs.html"

_MISSING_BUILD = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Money Machine · UI build missing</title>
<style>
body{background:#05070d;color:#e2e8f0;font-family:system-ui,sans-serif;display:grid;
place-items:center;min-height:100vh;margin:0}
main{max-width:620px;padding:40px;border:1px solid #1e293b;border-radius:20px;
background:#0b1120}
code{background:#111827;border:1px solid #1f2937;border-radius:6px;padding:2px 6px}
pre{background:#020617;border:1px solid #1f2937;border-radius:12px;padding:16px;
overflow:auto}
a{color:#34d399}
</style></head>
<body><main>
<h1>Modern dashboard not built yet</h1>
<p>The React dashboard lives in <code>web/</code>. Build it once:</p>
<pre>cd web
npm install
npm run build</pre>
<p>Then restart or refresh this page. The original dashboard is still available at
<a href="/">the classic UI</a>.</p>
</main></body></html>"""


@router.get("/ui", include_in_schema=False)
async def ui_root() -> RedirectResponse:
    return RedirectResponse(url="/ui/", status_code=307)


@router.get("/ui/docs.html", include_in_schema=False, response_model=None)
async def ui_docs():
    """Serve the standalone systems documentation (no dashboard login required)."""
    if not DOCS_FILE.exists():
        return HTMLResponse(
            "<!doctype html><meta charset='utf-8'><title>Documentation</title>"
            "<p>Documentation file web/docs.html is missing.</p>",
            status_code=404,
        )
    return FileResponse(DOCS_FILE, media_type="text/html; charset=utf-8")


@router.get("/ui/{path:path}", include_in_schema=False)
async def ui_spa(path: str):
    if not INDEX_FILE.exists():
        return HTMLResponse(_MISSING_BUILD, status_code=503)

    resolved_dist = DIST_DIR.resolve()
    if path:
        candidate = (DIST_DIR / path).resolve()
        try:
            candidate.relative_to(resolved_dist)
        except ValueError:
            return HTMLResponse("Not found", status_code=404)
        if candidate.is_file():
            return FileResponse(candidate)

    # Unknown paths are client-side routes (React Router), not 404s.
    return FileResponse(INDEX_FILE)
