"""Deterministic Mock OCR Adapter for Offline Testing and CI."""

from backend.app.integrations.ocr.base import OCRProvider, OCRResult
from backend.app.domain.receipt import ExpenseLine


class MockOCRAdapter(OCRProvider):
    """Fast, deterministic mock OCR engine requiring zero external network calls."""

    def __init__(self, default_confidence: float = 0.94):
        self.default_confidence = default_confidence

    def extract_receipt(self, file_bytes: bytes, filename: str = "receipt.jpg") -> OCRResult:
        # Generate realistic restaurant supplier expense items
        lines = [
            ExpenseLine(item_name="Fresh Salmon Fillet (kg)", quantity=5.0, unit_price=420.0, total_price=2100.0, category="seafood"),
            ExpenseLine(item_name="Jasmine Rice 5kg Bag", quantity=3.0, unit_price=180.0, total_price=540.0, category="dry_goods"),
            ExpenseLine(item_name="Cooking Oil (Palm 1L)", quantity=6.0, unit_price=45.0, total_price=270.0, category="condiments")
        ]
        total = sum(item.total_price for item in lines)

        return OCRResult(
            supplier_name="Siam Fresh Wholesale Ltd.",
            receipt_number="INV-2026-0919",
            receipt_date="2026-09-19",
            total_amount=total,
            currency="THB",
            confidence_score=self.default_confidence,
            lines=lines,
            raw_text="SIAM FRESH WHOLESALE LTD.\nINV-2026-0919\nSALMON 5KG 2100.00\nRICE 3BAG 540.00\nOIL 6BTL 270.00\nTOTAL: 2910.00 THB"
        )
