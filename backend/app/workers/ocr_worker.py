"""Background Async Worker for Receipt OCR Processing."""

import os
import time
import logging
from typing import Optional
from backend.app.domain.receipt import (
    ReceiptRecord, ReceiptStatus, ReceiptStateMachine
)
from backend.app.integrations.ocr.base import OCRProvider
from backend.app.integrations.ocr.mock_adapter import MockOCRAdapter
from backend.app.integrations.storage.base import LocalStorageAdapter
from backend.app.api.receipts import RECEIPTS_DB

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ocr-worker")


class ReceiptOCRWorker:
    """Consumes receipt jobs and executes OCR processing through OCRProvider."""

    def __init__(
        self,
        queue_name: str = "receipt_ocr",
        ocr_provider: Optional[OCRProvider] = None,
        storage_adapter: Optional[LocalStorageAdapter] = None
    ):
        self.queue_name = queue_name
        self.ocr = ocr_provider or MockOCRAdapter()
        self.storage = storage_adapter or LocalStorageAdapter(base_dir="./uploads-temp")
        self.running = False

    def process_single_receipt(self, receipt_id: str) -> Optional[ReceiptRecord]:
        """Processes one queued receipt through the state machine."""
        record = RECEIPTS_DB.get(receipt_id)
        if not record:
            logger.warning("Receipt %s not found in database.", receipt_id)
            return None

        # 1. Transition QUEUED -> OCR_RUNNING
        record.status = ReceiptStateMachine.transition(record.status, ReceiptStatus.OCR_RUNNING)
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

            return record

        except Exception as exc:
            logger.error("Error processing receipt %s: %s", receipt_id, exc)
            record.status = ReceiptStateMachine.transition(record.status, ReceiptStatus.FAILED)
            return record

    def run_worker_loop(self, poll_interval: float = 2.0, max_iterations: Optional[int] = None):
        """Worker execution loop polling the queue."""
        logger.info("Starting OCR Worker loop on queue: '%s'...", self.queue_name)
        self.running = True
        iterations = 0

        while self.running:
            # Find any receipts currently in QUEUED state
            queued = [r.id for r in RECEIPTS_DB.values() if r.status == ReceiptStatus.QUEUED]
            for r_id in queued:
                self.process_single_receipt(r_id)

            iterations += 1
            if max_iterations and iterations >= max_iterations:
                break
            time.sleep(poll_interval)


if __name__ == "__main__":
    queue_name = os.getenv("QUEUE_NAME", "receipt_ocr")
    worker = ReceiptOCRWorker(queue_name=queue_name)
    worker.run_worker_loop()
