"""Tests for Async OCR Worker."""

import unittest
from backend.app.domain.receipt import ReceiptRecord, ReceiptStatus
from backend.app.workers.ocr_worker import ReceiptOCRWorker
from backend.app.integrations.ocr.mock_adapter import MockOCRAdapter
from backend.app.integrations.storage.base import LocalStorageAdapter
from backend.app.api.receipts import RECEIPTS_DB


class TestOCRWorker(unittest.TestCase):
    def setUp(self):
        self.storage = LocalStorageAdapter(base_dir="./uploads-temp/test")
        self.storage.store_file("test_receipt.jpg", b"mock_receipt_image_data")
        self.worker = ReceiptOCRWorker(
            queue_name="receipt_ocr",
            ocr_provider=MockOCRAdapter(default_confidence=0.92),
            storage_adapter=self.storage
        )

    def test_worker_processes_queued_receipt_to_approved(self):
        record = ReceiptRecord(
            id="rcpt_test_001",
            status=ReceiptStatus.QUEUED,
            image_storage_key="test_receipt.jpg"
        )
        RECEIPTS_DB["rcpt_test_001"] = record

        processed = self.worker.process_single_receipt("rcpt_test_001")
        self.assertIsNotNone(processed)
        self.assertEqual(processed.status, ReceiptStatus.APPROVED)
        self.assertEqual(processed.supplier_name, "Siam Fresh Wholesale Ltd.")
        self.assertGreater(processed.total_amount, 0)
        self.assertEqual(len(processed.lines), 3)

    def test_worker_flags_low_confidence_for_review(self):
        low_conf_worker = ReceiptOCRWorker(
            queue_name="receipt_ocr",
            ocr_provider=MockOCRAdapter(default_confidence=0.75),
            storage_adapter=self.storage
        )
        record = ReceiptRecord(
            id="rcpt_test_002",
            status=ReceiptStatus.QUEUED,
            image_storage_key="test_receipt.jpg"
        )
        RECEIPTS_DB["rcpt_test_002"] = record

        processed = low_conf_worker.process_single_receipt("rcpt_test_002")
        self.assertIsNotNone(processed)
        self.assertEqual(processed.status, ReceiptStatus.REVIEW_REQUIRED)


if __name__ == "__main__":
    unittest.main()
