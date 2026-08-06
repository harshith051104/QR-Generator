import os
import json
import uuid
import logging
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

logger = logging.getLogger("certificate_verifier")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_config():
    return {
        "sheet_id": os.getenv("GOOGLE_SHEET_ID", "").strip(),
        "sheet_name": os.getenv("GOOGLE_SHEET_NAME", "Certificates").strip(),
        "credentials_path": os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials/service_account.json").strip(),
        "credentials_json": os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip(),
        "base_url": os.getenv("BASE_URL", "http://localhost:8000").strip().rstrip("/")
    }

def get_gspread_client():
    config = get_config()
    cred_json_str = config["credentials_json"]
    cred_path = config["credentials_path"]

    errors = []

    # 1. Try reading from GOOGLE_CREDENTIALS_JSON env var (Vercel / Render)
    if cred_json_str:
        try:
            cleaned_json = cred_json_str.strip().strip("'\"")
            try:
                info = json.loads(cleaned_json, strict=False)
            except Exception:
                fixed_json = cleaned_json.replace('\r\n', '\\n').replace('\n', '\\n')
                info = json.loads(fixed_json, strict=False)

            if isinstance(info, str):
                info = json.loads(info, strict=False)
            if isinstance(info, dict) and "private_key" in info:
                info["private_key"] = info["private_key"].replace('\\n', '\n')
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
            return gspread.authorize(creds)
        except Exception as e:
            err_msg = f"GOOGLE_CREDENTIALS_JSON env var error: {e}"
            logger.error(err_msg)
            errors.append(err_msg)

    # 2. Try reading from file path (Local dev)
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    abs_cred_path = os.path.normpath(cred_path if os.path.isabs(cred_path) else os.path.join(base_dir, cred_path))

    if os.path.exists(abs_cred_path):
        try:
            with open(abs_cred_path, "r", encoding="utf-8") as f:
                info = json.load(f)
            if isinstance(info, dict) and "private_key" in info:
                info["private_key"] = info["private_key"].replace('\\n', '\n')
            creds = Credentials.from_service_account_info(info, scopes=SCOPES)
            return gspread.authorize(creds)
        except Exception as e:
            err_msg = f"Credentials file error at '{abs_cred_path}': {e}"
            logger.error(err_msg)
            errors.append(err_msg)
    else:
        errors.append(f"Credentials file not found at '{abs_cred_path}'")

    details = " | ".join(errors)
    raise FileNotFoundError(
        f"Google Service Account credentials not found or invalid. Details: [{details}]. "
        f"Please set GOOGLE_CREDENTIALS_JSON in Vercel settings or place service_account.json at '{cred_path}'."
    )

def get_worksheet():
    config = get_config()
    sheet_id = config["sheet_id"]
    sheet_name = config["sheet_name"]

    if not sheet_id or sheet_id == "your_google_sheet_id_here":
        raise ValueError(
            "GOOGLE_SHEET_ID is not configured in environment variables. "
            "Please specify a valid GOOGLE_SHEET_ID."
        )

    client = get_gspread_client()
    
    try:
        spreadsheet = client.open_by_key(sheet_id)
    except Exception:
        spreadsheet = client.open(sheet_id)

    try:
        worksheet = spreadsheet.worksheet(sheet_name)
    except Exception:
        worksheet = spreadsheet.sheet1

    return worksheet

def normalize_record(row_dict: dict) -> dict:
    """Normalize headers to standard key names."""
    lowered = {str(k).strip().lower(): v for k, v in row_dict.items()}

    def find_val(possible_keys, default=""):
        for pk in possible_keys:
            if pk.lower() in lowered:
                return str(lowered[pk.lower()]).strip()
        return default

    cert_num = find_val(["Certificate Number", "Certificate ID", "Cert Number", "Cert ID"])
    token = find_val(["Verification Token", "Token", "UUID"])
    qr_url = find_val(["QR URL", "QR Code URL", "QR_URL"])
    name = find_val(["Name", "Recipient Name", "Student Name"])
    course = find_val(["Course", "Course Name", "Program"])
    issue_date = find_val(["Issue Date", "Date", "Issued Date"])
    company = find_val(["Company", "Issued By", "Organization"])
    status = find_val(["Status", "State"], "Verified")

    return {
        "certificate_number": cert_num,
        "verification_token": token,
        "qr_url": qr_url,
        "name": name,
        "course": course,
        "issue_date": issue_date,
        "company": company,
        "status": status
    }

def fetch_all_certificates() -> list:
    """Fetch all certificate rows from Google Sheet."""
    worksheet = get_worksheet()
    all_records = worksheet.get_all_records()
    
    certificates = []
    for r in all_records:
        norm = normalize_record(r)
        if norm["certificate_number"] or norm["verification_token"] or norm["name"]:
            certificates.append(norm)
            
    return certificates

def auto_fill_missing_tokens_and_urls() -> list:
    """
    Check all rows in Google Sheet.
    For any row with missing fields, auto-fill:
      - Verification Token  → secure UUID4
      - QR URL              → BASE_URL/verify/<token>
      - Issue Date          → today's date (DD Mon YYYY)
      - Company             → COMPANY_NAME env var (default: ABC)
    Creates the columns in the sheet header if they don't exist yet.
    Returns the refreshed list of certificate dicts.
    """
    from datetime import date as _date

    config = get_config()
    base_url = config["base_url"]
    company_name = os.getenv("COMPANY_NAME", "ABC").strip()
    today_str = _date.today().strftime("%d %b %Y")   # e.g. "06 Aug 2026"

    worksheet = get_worksheet()
    headers = worksheet.row_values(1)

    def find_col_idx(header_names):
        for name in header_names:
            for idx, h in enumerate(headers, start=1):
                if h.strip().lower() == name.lower():
                    return idx
        return None

    token_col    = find_col_idx(["Verification Token", "Token", "UUID"])
    qr_col       = find_col_idx(["QR URL", "QR Code URL", "QR_URL"])
    date_col     = find_col_idx(["Issue Date", "Date", "Issued Date"])
    company_col  = find_col_idx(["Company", "Issued By", "Organization"])

    # ── Add missing columns to header row ──
    header_changed = False
    if not token_col:
        headers.append("Verification Token")
        token_col = len(headers)
        header_changed = True
    if not qr_col:
        headers.append("QR URL")
        qr_col = len(headers)
        header_changed = True
    if not date_col:
        headers.append("Issue Date")
        date_col = len(headers)
        header_changed = True
    if not company_col:
        headers.append("Company")
        company_col = len(headers)
        header_changed = True

    if header_changed:
        worksheet.update("1:1", [headers])
        logger.info(f"Sheet header updated: {headers}")

    rows = worksheet.get_all_records()
    cell_updates = []

    for row_idx, row in enumerate(rows, start=2):
        # Skip completely empty rows (no name, no cert number)
        name    = str(row.get("Name") or row.get("Recipient Name") or row.get("Student Name") or "").strip()
        cert_no = str(row.get("Certificate Number") or row.get("Certificate ID") or "").strip()
        if not name and not cert_no:
            continue

        # ── Verification Token ──
        token = str(row.get("Verification Token") or row.get("Token") or row.get("UUID") or "").strip()
        if not token:
            token = str(uuid.uuid4())
            cell_updates.append(gspread.Cell(row_idx, token_col, token))

        # ── QR URL ──
        expected_qr = f"{base_url}/verify/{token}"
        existing_qr = str(row.get("QR URL") or row.get("QR Code URL") or "").strip()
        if not existing_qr or existing_qr != expected_qr:
            cell_updates.append(gspread.Cell(row_idx, qr_col, expected_qr))

        # ── Issue Date ──
        existing_date = str(row.get("Issue Date") or row.get("Date") or row.get("Issued Date") or "").strip()
        if not existing_date:
            cell_updates.append(gspread.Cell(row_idx, date_col, today_str))

        # ── Company ──
        existing_company = str(row.get("Company") or row.get("Issued By") or row.get("Organization") or "").strip()
        if not existing_company:
            cell_updates.append(gspread.Cell(row_idx, company_col, company_name))

    if cell_updates:
        logger.info(f"Auto-filling {len(cell_updates)} cell(s) in Google Sheet…")
        worksheet.update_cells(cell_updates)

    return fetch_all_certificates()
