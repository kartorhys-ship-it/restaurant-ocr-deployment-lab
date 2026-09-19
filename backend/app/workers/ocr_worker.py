"""Background Async Worker for Receipt OCR Processing.

Consumes receipt OCR jobs from the inter-process queue (Redis / SQLite) and
persists extracted expense data into the shared database.
"""

import os
import time
import logging
from typing import Optional
from backend.app.domain.receipt import (
    ReceiptRecord, ReceiptStatus, ReceiptStateMachine
)
from backend.app.domain.db import get_receipt_store, ReceiptStore
from backend.app.domain.queue import get_receipt_queue, InterProcessQueue
from backend.app.integrations.ocr.base import OCRProvider
from backend.app.integrations.ocr.mock_adapter import MockOCRAdapter
from backend.app.integrations.storage.base import LocalStorageAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ocr-worker")


class ReceiptOCRWorker:
    """Consumes receipt jobs and executes OCR processing through OCRProvider."""

    def __init__(
        self,
        queue_name: str = "receipt_ocr",
        ocr_provider: Optional[OCRProvider] = None,
        storage_adapter: Optional[LocalStorageAdapter] = None,
        store: Optional[ReceiptStore] = None,
        queue: Optional[InterProcessQueue] = None,
        max_retries: Optional[int] = None
    ):
        self.queue_name = queue_name
        self.ocr = ocr_provider or MockOCRAdapter()
        storage_dir = os.getenv("STORAGE_DIR", "./uploads-temp")
        self.storage = storage_adapter or LocalStorageAdapter(base_dir=storage_dir)
        self.db = store or get_receipt_store()
        self.queue = queue or get_receipt_queue(queue_name=self.queue_name)
        self.max_retries = max_retries if max_retries is not None else int(os.getenv("MAX_RETRIES", "3"))
        self.running = False

    def process_single_receipt(self, receipt_id: str) -> Optional[ReceiptRecord]:
        """Processes one queued receipt through the state machine and persists updates."""
        record = self.db.get(receipt_id)
        if not record:
            logger.warning("Receipt %s not found in database.", receipt_id)
            return None

        # 1. Transition QUEUED -> OCR_RUNNING
        record.status = ReceiptStateMachine.transition(record.status, ReceiptStatus.OCR_RUNNING)
        self.db[receipt_id] = record
        logger.info("Processing receipt %s (Status: OCR_RUNNING)", receipt_id)

        try:
            # 2. Retrieve image bytes from storage
            image_bytes = self.storage.retrieve_file(record.image_storage_key)

            # 3. Execute OCR extraction
            result = self.ocr.extract_receipt(image_bytes, filename=record.image_storage_key)

            # 4. Populate structured expense data
            record.supplier_name = result.supplier_name
            record.receipt_number = result.receipt_number
            record.receipt_date = result.receipt_date
            record.total_amount = result.total_amount
            record.currency = result.currency
            record.confidence_score = result.confidence_score
            record.lines = result.lines

            # 5. Transition OCR_RUNNING -> PARSED
            record.status = ReceiptStateMachine.transition(record.status, ReceiptStatus.PARSED)

            # 6. Branch on confidence: REVIEW_REQUIRED vs APPROVED
            if result.confidence_score < 0.85:
                record.status = ReceiptStateMachine.transition(record.status, ReceiptStatus.REVIEW_REQUIRED)
                logger.info("Receipt %s flagged for review (Confidence: %.2f)", receipt_id, result.confidence_score)
            else:
                record.status = ReceiptStateMachine.transition(record.status, ReceiptStatus.APPROVED)
                logger.info("Receipt %s auto-approved (Confidence: %.2f)", receipt_id, result.confidence_score)

            # Persist finalized record to DB
            self.db[receipt_id] = record
            return record

        except Exception as exc:
            logger.error("Error processing receipt %s: %s", receipt_id, exc)
            record.status = ReceiptStateMachine.transition(record.status, ReceiptStatus.FAILED)
            self.db[receipt_id] = record
            return record

    def run_worker_loop(self, poll_interval: float = 1.0, max_iterations: Optional[int] = None):
        """Worker execution loop consuming from queue with retry policy and database fallback."""
        logger.info("Starting OCR Worker loop on queue: '%s'...", self.queue_name)
        self.running = True
        iterations = 0

        while self.running:
            # Primary path: dequeue from inter-process queue
            receipt_id = self.queue.dequeue(timeout=poll_interval)

            if receipt_id:
                logger.info("Dequeued job: %s", receipt_id)
                record = self.process_single_receipt(receipt_id)
                if record and record.status in (ReceiptStatus.APPROVED, ReceiptStatus.REVIEW_REQUIRED, ReceiptStatus.PARSED):
                    self.queue.mark_completed(receipt_id)
                else:
                    retries = self.queue.get_retry_count(receipt_id)
                    if retries < self.max_retries:
                        # Transition state machine: FAILED -> QUEUED
                        if record and record.status == ReceiptStatus.FAILED:
                            record.status = ReceiptStateMachine.transition(record.status, ReceiptStatus.QUEUED)
                            self.db[receipt_id] = record
                        new_retry_count = self.queue.mark_failed(
                            receipt_id,
                            error="OCR extraction failure; scheduled for retry",
                            can_retry=True
                        )
                        logger.warning(
                            "Receipt %s extraction failed; scheduled retry %d/%d",
                            receipt_id, new_retry_count, self.max_retries
                        )
                    else:
                        self.queue.mark_failed(
                            receipt_id,
                            error=f"Exceeded max retries ({self.max_retries})",
                            can_retry=False
                        )
                        logger.error(
                            "Receipt %s extraction permanently failed after %d retries",
                            receipt_id, self.max_retries
                        )
            else:
                # Fallback path: check for any unconsumed QUEUED receipts in database
                queued_records = [r.id for r in self.db.values() if r.status == ReceiptStatus.QUEUED]
                for q_id in queued_records:
                    self.process_single_receipt(q_id)

            iterations += 1
            if max_iterations and iterations >= max_iterations:
                break


if __name__ == "__main__":
    queue_name = os.getenv("QUEUE_NAME", "receipt_ocr")
    worker = ReceiptOCRWorker(queue_name=queue_name)
    worker.run_worker_loop()
