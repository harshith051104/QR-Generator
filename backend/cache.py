import os
import asyncio
import logging
from datetime import datetime
from backend.google_service import fetch_all_certificates

logger = logging.getLogger("certificate_verifier")

class CertificateCache:
    def __init__(self):
        self.by_token = {}
        self.by_number = {}
        self.last_updated = None
        self._refresh_task = None

    def load_cache(self):
        """Fetch records from Google Sheets and build fast O(1) lookup dictionaries."""
        logger.info("Loading certificate data from Google Sheets into memory cache...")
        try:
            records = fetch_all_certificates()
            
            token_dict = {}
            number_dict = {}

            for cert in records:
                token = cert.get("verification_token")
                cert_num = cert.get("certificate_number")

                if token:
                    token_dict[token.strip().lower()] = cert
                if cert_num:
                    number_dict[cert_num.strip().lower()] = cert

            self.by_token = token_dict
            self.by_number = number_dict
            self.last_updated = datetime.now()
            logger.info(f"Cache successfully loaded {len(records)} certificates. Last updated: {self.last_updated}")
            return len(records)
        except Exception as e:
            logger.error(f"Failed to load certificate cache: {e}")
            raise e

    def get_by_token(self, token: str):
        if not token:
            return None
        return self.by_token.get(token.strip().lower())

    def get_by_number(self, cert_number: str):
        if not cert_number:
            return None
        return self.by_number.get(cert_number.strip().lower())

    def search(self, query: str):
        """Search by token first, then by certificate number."""
        if not query:
            return None
        q = query.strip().lower()
        return self.by_token.get(q) or self.by_number.get(q)

    async def _auto_refresh_loop(self, interval_minutes: int):
        while True:
            await asyncio.sleep(interval_minutes * 60)
            logger.info(f"Running periodic {interval_minutes}-minute cache auto-refresh...")
            try:
                self.load_cache()
            except Exception as e:
                logger.error(f"Error during auto-refresh: {e}")

    def start_auto_refresh(self, interval_minutes: int = 5):
        if self._refresh_task is None or self._refresh_task.done():
            self._refresh_task = asyncio.create_task(self._auto_refresh_loop(interval_minutes))
            logger.info(f"Started background cache refresh task (every {interval_minutes} minutes).")

# Global singleton instance
certificate_cache = CertificateCache()
