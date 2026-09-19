import os
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from backend.app.compat import APIRouter, UploadFile, File, HTTPException, status
from backend.app.domain.receipt import (
    ReceiptRecord, ReceiptStatus, ReceiptStateMachine, ExpenseLine
)
from backend.app.domain.db import get_receipt_store, ReceiptStore
from backend.app.domain.queue import get_receipt_queue, InterProcessQueue
from backend.app.integrations.storage.base import LocalStorageAdapter

router = APIRouter(prefix="/api/receipts", tags=["receipts"])

# Persistent SQLite / SQLAlchemy store shared across processes
RECEIPTS_DB: ReceiptStore = get_receipt_store()
receipt_queue: InterProcessQueue = get_receipt_queue(queue_name=os.getenv("QUEUE_NAME", "receipt_ocr"))
storage = LocalStorageAdapter(base_dir=os.getenv("STORAGE_DIR", "./uploads-temp"))


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def upload_receipt(file: UploadFile = File(...)) -> Dict[str, Any]:
    """Uploads receipt image/PDF, stores in object storage, enqueues OCR job into persistent queue."""
    receipt_id = f"rcpt_{uuid.uuid4().hex[:12]}"
    file_bytes = await file.read()

    # 1. Store in object storage
    storage_key = f"receipts/{datetime.utcnow().strftime('%Y/%m')}/{receipt_id}_{file.filename}"
    storage.store_file(storage_key, file_bytes)

    # 2. Initialize receipt record in UPLOADED state
    record = ReceiptRecord(
        id=receipt_id,
        status=ReceiptStatus.UPLOADED,
        image_storage_key=storage_key
    )

    # 3. Transition to QUEUED state and persist in DB
    record.status = ReceiptStateMachine.transition(record.status, ReceiptStatus.QUEUED)
    RECEIPTS_DB[receipt_id] = record

    # 4. Enqueue into persistent inter-process queue
    receipt_queue.enqueue(receipt_id)

    return {
        "receipt_id": receipt_id,
        "status": record.status.value,
        "queue": receipt_queue.queue_name,
        "message": "Receipt accepted and queued for asynchronous OCR extraction."
    }


@router.get("", response_model=List[ReceiptRecord])
def list_receipts() -> List[ReceiptRecord]:
    """Lists all receipts in database."""
    return list(RECEIPTS_DB.values())


@router.get("/{receipt_id}", response_model=ReceiptRecord)
def get_receipt(receipt_id: str) -> ReceiptRecord:
    """Retrieves specific receipt record by ID."""
    record = RECEIPTS_DB.get(receipt_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Receipt '{receipt_id}' not found.")
    return record


@router.post("/{receipt_id}/approve", response_model=ReceiptRecord)
def approve_receipt(receipt_id: str) -> ReceiptRecord:
    """Human approval transition for receipts flagged for review."""
    record = RECEIPTS_DB.get(receipt_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Receipt '{receipt_id}' not found.")

    record.status = ReceiptStateMachine.transition(record.status, ReceiptStatus.APPROVED)
    record.updated_at = datetime.utcnow()
    RECEIPTS_DB[receipt_id] = record
    return record
