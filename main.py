import os
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Form, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
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
    file_full_path = os.path.join(STATIC_DIR, file_path)
    if not os.path.exists(file_full_path):
        file_full_path = os.path.join(os.getcwd(), "static", file_path)
    if os.path.exists(file_full_path):
        mime = "text/css" if file_path.endswith(".css") else ("image/svg+xml" if file_path.endswith(".svg") else None)
        return FileResponse(file_full_path, media_type=mime)
    return Response(status_code=status.HTTP_404_NOT_FOUND)

@app.get("/", response_class=HTMLResponse)
@app.get("/api/index.py", response_class=HTMLResponse)
async def home(request: Request):
    """Render search portal landing page."""
    ensure_cache_loaded()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"company_name": COMPANY_NAME}
    )

@app.post("/verify")
@app.post("/api/index.py")
async def verify_post(query: str = Form(...)):
    """Handle form submission from search box."""
    clean_query = query.strip()
    return RedirectResponse(url=f"/verify/{clean_query}", status_code=status.HTTP_303_SEE_OTHER)

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

    if cert and cert.get("status", "").lower() in ["verified", "valid"]:
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
