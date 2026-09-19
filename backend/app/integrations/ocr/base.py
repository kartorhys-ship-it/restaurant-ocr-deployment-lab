from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from backend.app.compat import BaseModel, Field
from backend.app.domain.receipt import ExpenseLine


class OCRResult(BaseModel):
    supplier_name: str
    receipt_number: Optional[str] = None
    receipt_date: Optional[str] = None
    total_amount: float
    currency: str = "THB"
    confidence_score: float = Field(ge=0.0, le=1.0)
    lines: List[ExpenseLine] = Field(default_factory=list)
    raw_text: str = ""


class OCRProvider(ABC):
    @abstractmethod
    def extract_receipt(self, file_bytes: bytes, filename: str = "receipt.jpg") -> OCRResult:
        """Processes raw receipt image or PDF bytes and returns structured OCR result."""
        raise NotImplementedError
