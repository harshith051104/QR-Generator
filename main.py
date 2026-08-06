import os
import logging
import urllib.parse
from typing import Optional
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from backend.cache import certificate_cache

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("main")

COMPANY_NAME = os.getenv("COMPANY_NAME", "Tech Academy")
REFRESH_MINUTES = int(os.getenv("CACHE_REFRESH_MINUTES", "5"))

# Absolute directory paths for Vercel Serverless compatibility
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Load Google Sheet into memory cache
    logger.info("Initializing Certificate Verification Application...")
    try:
        certificate_cache.load_cache()
        # Only start background auto-refresh loop if not running in Vercel serverless environment
        if not os.getenv("VERCEL"):
            certificate_cache.start_auto_refresh(interval_minutes=REFRESH_MINUTES)
    except Exception as e:
        logger.warning(
            f"Could not load Google Sheet cache on startup: {e}. "
            "Please check GOOGLE_SHEET_ID and GOOGLE_CREDENTIALS_JSON in Vercel environment settings."
        )
    yield
    logger.info("Shutting down Certificate Verification Application...")

app = FastAPI(
    title="Certificate Verification System",
    description="Fast, reliable QR-code based certificate authenticity verification using Google Sheets & memory cache.",
    version="2.0.0",
    lifespan=lifespan
)

# Mount static directory safely
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

def ensure_cache_loaded():
    """Ensure cache is loaded on serverless cold starts if not already populated."""
    if certificate_cache.last_updated is None:
        try:
            certificate_cache.load_cache()
        except Exception as e:
            logger.error(f"Lazy cache load failed: {e}")

@app.middleware("http")
async def vercel_path_rewrite_middleware(request: Request, call_next):
    raw_path = request.scope.get("path", "")
    # Only rewrite when Vercel has routed the request to the /api/index.py function
    if raw_path.startswith("/api/index"):
        # Recover the original request path using a priority-ordered header chain.
        #
        # vercel.json uses "source": "/:path*" which is a NAMED parameter.
        # Vercel then sets x-now-route-matches = "path=<encoded-value>" reliably.
        #
        # Priority:
        #   1. x-now-route-matches  – named capture from vercel.json ":path*"
        #   2. x-forwarded-uri      – Vercel edge header (full original URI)
        #   3. x-original-uri       – fallback on some Vercel regions
        #   4. raw-path ASGI scope  – byte-string of the raw path
        clean_path = None

        route_matches = request.headers.get("x-now-route-matches", "")
        if route_matches:
            # Format: "path=<percent-encoded-value>&next=..."
            for part in route_matches.split("&"):
                if part.startswith("path="):
                    encoded = part[len("path="):].split("?")[0]
                    decoded = urllib.parse.unquote(encoded)
                    if decoded:
                        clean_path = decoded if decoded.startswith("/") else "/" + decoded
                    break

        if not clean_path:
            for header in ("x-forwarded-uri", "x-original-uri"):
                val = request.headers.get(header, "")
                if val:
                    clean_path = urllib.parse.unquote(val).split("?")[0] or "/"
                    break

        if not clean_path:
            raw_bytes = request.scope.get("raw_path", b"")
            if raw_bytes:
                candidate = urllib.parse.unquote(
                    raw_bytes.decode("utf-8", errors="replace")
                ).split("?")[0]
                if candidate not in ("/api/index.py", "/api/index", "/api", ""):
                    clean_path = candidate

        if not clean_path or clean_path in ("/api/index.py", "/api/index", "/api", ""):
            clean_path = "/"

        logger.info(f"[Vercel] Rewrote path: {raw_path!r} → {clean_path!r} "
                    f"(route_matches={request.headers.get('x-now-route-matches', 'none')!r})")
        request.scope["path"] = clean_path
        request.scope["root_path"] = ""

    return await call_next(request)

@app.get('/favicon.ico', include_in_schema=False)
@app.get('/favicon.png', include_in_schema=False)
async def favicon():
    logo_path = os.path.join(STATIC_DIR, "logo.svg")
    if not os.path.exists(logo_path):
        logo_path = os.path.join(os.getcwd(), "static", "logo.svg")
    if os.path.exists(logo_path):
        return FileResponse(logo_path, media_type="image/svg+xml")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@app.get("/static/{file_path:path}", include_in_schema=False)
async def serve_static(file_path: str):
    mime_map = {
        ".css":  "text/css",
        ".js":   "application/javascript",
        ".svg":  "image/svg+xml",
        ".png":  "image/png",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".ico":  "image/x-icon",
        ".woff": "font/woff",
        ".woff2":"font/woff2",
    }
    ext = os.path.splitext(file_path)[1].lower()
    mime = mime_map.get(ext, "application/octet-stream")

    for base in (STATIC_DIR, os.path.join(os.getcwd(), "static")):
        full = os.path.join(base, file_path)
        if os.path.exists(full):
            return FileResponse(full, media_type=mime)

    logger.warning(f"Static file not found: {file_path} (looked in {STATIC_DIR})")
    return Response(status_code=status.HTTP_404_NOT_FOUND)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render search portal landing page."""
    ensure_cache_loaded()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"company_name": COMPANY_NAME}
    )

@app.post("/", response_class=HTMLResponse)
async def home_post(request: Request, query: Optional[str] = Form(None)):
    """Fallback POST handler for / in case Vercel path recovery defaults to root.
    Processes the search form and redirects to /verify/<query>.
    """
    target_query = (query or "").strip()
    if not target_query:
        try:
            form = await request.form()
            target_query = str(form.get("query", "")).strip()
        except Exception:
            pass
    if not target_query:
        target_query = request.query_params.get("query", "").strip()
    if target_query:
        return RedirectResponse(url=f"/verify/{target_query}", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/verify")
@app.post("/verify")
async def verify_post(request: Request, query: Optional[str] = Form(None)):
    """Handle form submission from search box."""
    target_query = (query or "").strip()
    if not target_query:
        target_query = request.query_params.get("query", "").strip()
    if not target_query:
        try:
            form = await request.form()
            target_query = str(form.get("query", "")).strip()
        except Exception:
            pass

    if target_query:
        return RedirectResponse(url=f"/verify/{target_query}", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/verify/{query}", response_class=HTMLResponse)
async def verify_certificate(request: Request, query: str, response: Response):
    """
    Verification endpoint.
    Look up by verification token or certificate number.
    Returns 200 OK + verified.html if genuine.
    Returns 404 Not Found + invalid.html if missing or revoked.
    """
    ensure_cache_loaded()
    cert = certificate_cache.search(query)

    cert_status = str(cert.get("status") or "").strip().lower() if cert else ""
    is_valid = cert and (cert_status not in ["invalid", "revoked", "expired", "fake", "denied"])

    if cert and is_valid:
        now_str = datetime.now().strftime("%d %b %Y %H:%M:%S") + " IST"
        return templates.TemplateResponse(
            request=request,
            name="verified.html",
            context={
                "cert": cert,
                "company_name": COMPANY_NAME,
                "verified_at": now_str
            },
            status_code=status.HTTP_200_OK
        )
    
    # Not found or revoked
    response.status_code = status.HTTP_404_NOT_FOUND
    return templates.TemplateResponse(
        request=request,
        name="invalid.html",
        context={
            "company_name": COMPANY_NAME,
            "query": query
        },
        status_code=status.HTTP_404_NOT_FOUND
    )

@app.post("/refresh-cache")
async def refresh_cache():
    """Manual endpoint to refresh the memory cache from Google Sheets."""
    try:
        count = certificate_cache.load_cache()
        return {
            "status": "success",
            "message": f"Successfully reloaded {count} certificate records.",
            "last_updated": certificate_cache.last_updated.isoformat() if certificate_cache.last_updated else None
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
