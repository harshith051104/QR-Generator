import os
import logging
import qrcode
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("certificate_verifier")

def get_base_url():
    return os.getenv("BASE_URL", "http://localhost:8000").strip().rstrip("/")

def generate_qr_code(token: str, output_dir: str = "qr_codes", force: bool = False) -> str:
    """
    Generate a QR code image for a verification token.
    The QR content will be BASE_URL + '/verify/' + token.
    Saves image to output_dir/<token>.png.
    Skips if file already exists unless force=True.
    """
    if not token:
        raise ValueError("Token cannot be empty")

    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"{token}.png")

    if os.path.exists(filepath) and not force:
        logger.debug(f"QR code already exists for token: {token}")
        return filepath

    base_url = get_base_url()
    verify_url = f"{base_url}/verify/{token}"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(verify_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#1E293B", back_color="#FFFFFF") # Deep slate blue on crisp white background
    img.save(filepath)
    logger.info(f"Generated QR code: {filepath} -> {verify_url}")
    return filepath

def generate_all_qrs(certificates: list, output_dir: str = "qr_codes") -> dict:
    """
    Iterate over certificate records and generate QR codes for each token.
    Returns stats dict with 'generated', 'skipped', and 'errors'.
    """
    stats = {"generated": 0, "skipped": 0, "errors": 0}

    for cert in certificates:
        token = cert.get("verification_token")
        if not token:
            continue

        try:
            filepath = os.path.join(output_dir, f"{token}.png")
            if os.path.exists(filepath):
                stats["skipped"] += 1
            else:
                generate_qr_code(token, output_dir=output_dir)
                stats["generated"] += 1
        except Exception as e:
            logger.error(f"Error generating QR for token '{token}': {e}")
            stats["errors"] += 1

    return stats
