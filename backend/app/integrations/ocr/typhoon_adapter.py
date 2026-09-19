"""Production Typhoon OCR Adapter."""

import os
from typing import Optional
from backend.app.integrations.ocr.base import OCRProvider, OCRResult


class TyphoonOCRAdapter(OCRProvider):
    """Production Typhoon OCR integration using external vision API."""

    def __init__(self, api_key: Optional[str] = None, endpoint_url: Optional[str] = None):
        self.api_key = api_key or os.getenv("OCR_API_KEY", "")
        self.endpoint_url = endpoint_url or os.getenv("OCR_ENDPOINT_URL", "https://api.opentyphoon.ai/v1/vision/ocr")

    def extract_receipt(self, file_bytes: bytes, filename: str = "receipt.jpg") -> OCRResult:
        if not self.api_key:
            raise ValueError("TyphoonOCRAdapter requires 'OCR_API_KEY' environment variable or token.")
        
        # In a real deployed environment with live internet and valid API key:
        # response = httpx.post(self.endpoint_url, headers={"Authorization": f"Bearer {self.api_key}"}, files={"file": file_bytes})
        # return parse_typhoon_response(response.json())
        raise NotImplementedError("Live Typhoon OCR API calls require a valid production key.")
