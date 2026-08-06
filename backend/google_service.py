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
            cleaned_json = cleaned_json.replace('\\n', '\n')
            info = json.loads(cleaned_json)
            if isinstance(info, str):
                info = json.loads(info)
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
    If 'Verification Token' or 'QR URL' is missing:
    - Generate a secure UUID4 token
    - Construct QR URL using BASE_URL
    - Update Google Sheet in batch
    Returns updated list of certificate dicts.
    """
    config = get_config()
    base_url = config["base_url"]
    worksheet = get_worksheet()

    headers = worksheet.row_values(1)
    
    def find_col_idx(header_names, default_name):
        for name in header_names:
            for idx, h in enumerate(headers, start=1):
                if h.strip().lower() == name.lower():
                    return idx
        return None

    token_col = find_col_idx(["Verification Token", "Token", "UUID"], "Verification Token")
    qr_col = find_col_idx(["QR URL", "QR Code URL", "QR_URL"], "QR URL")

    updates_to_header = False
    if not token_col:
        headers.append("Verification Token")
        token_col = len(headers)
        updates_to_header = True
    if not qr_col:
        headers.append("QR URL")
        qr_col = len(headers)
        updates_to_header = True

    if updates_to_header:
        worksheet.update("1:1", [headers])

    rows = worksheet.get_all_records()
    cell_updates = []

    for row_idx, row in enumerate(rows, start=2):
        token = str(row.get("Verification Token") or row.get("Token") or "").strip()
        qr_url = str(row.get("QR URL") or "").strip()
        
        needs_token_update = not token
        if needs_token_update:
            token = str(uuid.uuid4())
            cell_updates.append(gspread.Cell(row_idx, token_col, token))

        expected_qr_url = f"{base_url}/verify/{token}"
        if not qr_url or qr_url != expected_qr_url:
            cell_updates.append(gspread.Cell(row_idx, qr_col, expected_qr_url))

    if cell_updates:
        logger.info(f"Updating {len(cell_updates)} cell(s) in Google Sheet...")
        worksheet.update_cells(cell_updates)

    return fetch_all_certificates()
