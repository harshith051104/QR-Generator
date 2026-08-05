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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Load Google Sheet into memory cache
    logger.info("Initializing Certificate Verification Application...")
    try:
        certificate_cache.load_cache()
        certificate_cache.start_auto_refresh(interval_minutes=REFRESH_MINUTES)
    except Exception as e:
        logger.warning(
            f"Could not load Google Sheet cache on startup: {e}. "
            "Please ensure credentials/service_account.json and GOOGLE_SHEET_ID are properly set."
        )
    yield
    # Shutdown
    logger.info("Shutting down Certificate Verification Application...")

app = FastAPI(
    title="Certificate Verification System",
    description="Fast, reliable QR-code based certificate authenticity verification using Google Sheets & memory cache.",
    version="2.0.0",
    lifespan=lifespan
)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Render search portal landing page."""
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "company_name": COMPANY_NAME}
    )

@app.post("/verify")
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
    cert = certificate_cache.search(query)

    if cert and cert.get("status", "").lower() in ["verified", "valid"]:
        now_str = datetime.now().strftime("%d %b %Y %H:%M:%S") + " IST"
        return templates.TemplateResponse(
            "verified.html",
            {
                "request": request,
                "cert": cert,
                "company_name": COMPANY_NAME,
                "verified_at": now_str
            },
            status_code=status.HTTP_200_OK
        )
    
    # Not found or revoked
    response.status_code = status.HTTP_404_NOT_FOUND
    return templates.TemplateResponse(
        "invalid.html",
        {
            "request": request,
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
