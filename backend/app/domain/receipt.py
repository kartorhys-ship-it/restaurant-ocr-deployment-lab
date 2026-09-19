"""Receipt Domain Models and State Machine."""

from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime
from backend.app.compat import BaseModel, Field


class ReceiptStatus(str, Enum):
    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    OCR_RUNNING = "OCR_RUNNING"
    PARSED = "PARSED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    APPROVED = "APPROVED"
    FAILED = "FAILED"


class ReceiptStateTransitionError(Exception):
    """Raised when an illegal receipt state transition is attempted."""
    pass


class ReceiptStateMachine:
    """Explicit deterministic state machine for receipt processing lifecycle."""

    ALLOWED_TRANSITIONS = {
        ReceiptStatus.UPLOADED: {ReceiptStatus.QUEUED, ReceiptStatus.FAILED},
        ReceiptStatus.QUEUED: {ReceiptStatus.OCR_RUNNING, ReceiptStatus.FAILED},
        ReceiptStatus.OCR_RUNNING: {ReceiptStatus.PARSED, ReceiptStatus.FAILED},
        ReceiptStatus.PARSED: {ReceiptStatus.REVIEW_REQUIRED, ReceiptStatus.APPROVED, ReceiptStatus.FAILED},
        ReceiptStatus.REVIEW_REQUIRED: {ReceiptStatus.APPROVED, ReceiptStatus.FAILED},
        ReceiptStatus.APPROVED: set(),  # Terminal state
        ReceiptStatus.FAILED: {ReceiptStatus.QUEUED}  # Retry path
    }

    @classmethod
    def can_transition(cls, current: ReceiptStatus, target: ReceiptStatus) -> bool:
        return target in cls.ALLOWED_TRANSITIONS.get(current, set())

    @classmethod
    def transition(cls, current: ReceiptStatus, target: ReceiptStatus) -> ReceiptStatus:
        if not cls.can_transition(current, target):
            raise ReceiptStateTransitionError(
                f"Illegal receipt state transition: '{current.value}' -> '{target.value}'. "
                f"Allowed transitions from '{current.value}': {[s.value for s in cls.ALLOWED_TRANSITIONS.get(current, set())]}"
            )
        return target


# --- Data Models ---

class ExpenseLine(BaseModel):
    item_name: str
    quantity: float = 1.0
    unit_price: float
    total_price: float
    category: str = "general_supplies"


class ReceiptRecord(BaseModel):
    id: str
    supplier_name: Optional[str] = None
    receipt_number: Optional[str] = None
    receipt_date: Optional[str] = None
    total_amount: float = 0.0
    currency: str = "THB"
    confidence_score: float = 0.0
    status: ReceiptStatus = ReceiptStatus.UPLOADED
    image_storage_key: str
    lines: List[ExpenseLine] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
