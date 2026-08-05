#!/usr/bin/env python3
"""
CLI Script to:
1. Connect to Google Sheets
2. Auto-generate UUID4 tokens and QR URLs for rows missing them
3. Update Google Sheet
4. Generate PNG QR code images in qr_codes/
"""
import sys
import logging
from backend.google_service import auto_fill_missing_tokens_and_urls
from backend.qr_generator import generate_all_qrs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("generate_qr")

def main():
    print("=" * 60)
    print("      QR Code Certificate Verification - Generator Script")
    print("=" * 60)

    try:
        logger.info("Connecting to Google Sheets & auto-filling missing tokens/URLs...")
        certificates = auto_fill_missing_tokens_and_urls()
        print(f"✅ Found {len(certificates)} certificate records in Google Sheet.")

        logger.info("Generating QR codes in 'qr_codes/' directory...")
        stats = generate_all_qrs(certificates, output_dir="qr_codes")

        print("\n--- Execution Summary ---")
        print(f"  • Total Certificates : {len(certificates)}")
        print(f"  • New QRs Generated  : {stats['generated']}")
        print(f"  • QRs Skipped (Exist): {stats['skipped']}")
        print(f"  • Errors Encounted   : {stats['errors']}")
        print("--------------------------\n")
        print("🎉 Script completed successfully! QR code files are stored in 'qr_codes/'.\n")

    except FileNotFoundError as fnf:
        logger.error(f"\n❌ Configuration Error: {fnf}")
        logger.error("Please place your Google service account JSON file in credentials/service_account.json\n")
        sys.exit(1)
    except ValueError as ve:
        logger.error(f"\n❌ Setup Error: {ve}\n")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Unexpected Error: {e}\n", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
