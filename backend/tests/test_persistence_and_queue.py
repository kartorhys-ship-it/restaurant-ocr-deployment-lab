"""Tests for Inter-Process Persistence and Queueing Layer."""

import os
import tempfile
import unittest
from datetime import datetime
from backend.app.domain.receipt import ReceiptRecord, ReceiptStatus, ExpenseLine
from backend.app.domain.db import SQLiteReceiptRepository, ReceiptStore
from backend.app.domain.queue import InterProcessQueue
from backend.app.workers.ocr_worker import ReceiptOCRWorker
from backend.app.integrations.ocr.mock_adapter import MockOCRAdapter
from backend.app.integrations.storage.base import LocalStorageAdapter


class TestPersistenceAndQueue(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "test_receipts.db")
        self.storage_dir = os.path.join(self.tmp_dir.name, "storage")
        os.makedirs(self.storage_dir, exist_ok=True)

        self.repo = SQLiteReceiptRepository(db_path=self.db_path)
        self.store = ReceiptStore(db_path=self.db_path)
        self.queue = InterProcessQueue(queue_name="test_queue", db_path=self.db_path)
        self.storage = LocalStorageAdapter(base_dir=self.storage_dir)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_receipt_persistence_crud(self):
        """Validates that ReceiptRecord is persisted and restored with all properties."""
        lines = [
            ExpenseLine(item_name="Tomatoes", quantity=10, unit_price=25.0, total_price=250.0),
            ExpenseLine(item_name="Cilantro", quantity=2, unit_price=15.0, total_price=30.0)
        ]
        record = ReceiptRecord(
            id="rcpt_persist_01",
            supplier_name="Talaad Thai Fresh",
            receipt_number="INV-2026-99",
            receipt_date="2026-09-20",
            total_amount=280.0,
            currency="THB",
            confidence_score=0.96,
            status=ReceiptStatus.UPLOADED,
            image_storage_key="test_img.jpg",
            lines=lines
        )

        self.repo.save(record)

        # Retrieve from another instance pointing to the same SQLite file
        loaded = self.repo.get("rcpt_persist_01")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.supplier_name, "Talaad Thai Fresh")
        self.assertEqual(loaded.receipt_number, "INV-2026-99")
        self.assertEqual(loaded.total_amount, 280.0)
        self.assertEqual(len(loaded.lines), 2)
        self.assertEqual(loaded.lines[0].item_name, "Tomatoes")
        self.assertEqual(loaded.status, ReceiptStatus.UPLOADED)

    def test_queue_enqueue_dequeue_lifecycle(self):
        """Validates FIFO enqueue, dequeue, and completion tracking."""
        self.queue.clear()
        self.assertEqual(self.queue.pending_count(), 0)

        self.queue.enqueue("job_alpha")
        self.queue.enqueue("job_beta")
        self.assertEqual(self.queue.pending_count(), 2)

        # Dequeue FIFO
        first = self.queue.dequeue()
        self.assertEqual(first, "job_alpha")
        self.queue.mark_completed("job_alpha")

        second = self.queue.dequeue()
        self.assertEqual(second, "job_beta")
        self.queue.mark_completed("job_beta")

        # Empty
        third = self.queue.dequeue(timeout=0.1)
        self.assertIsNone(third)

    def test_worker_consumes_from_persistent_queue(self):
        """End-to-end multi-process simulation: API enqueues, Worker processes."""
        self.storage.store_file("invoice_scan.jpg", b"fake_invoice_binary")
        record = ReceiptRecord(
            id="rcpt_multi_proc_01",
            status=ReceiptStatus.QUEUED,
            image_storage_key="invoice_scan.jpg"
        )
        self.store["rcpt_multi_proc_01"] = record
        self.queue.enqueue("rcpt_multi_proc_01")

        worker = ReceiptOCRWorker(
            queue_name="test_queue",
            ocr_provider=MockOCRAdapter(default_confidence=0.95),
            storage_adapter=self.storage,
            store=self.store,
            queue=self.queue
        )

        # Run single iteration of worker loop
        worker.run_worker_loop(poll_interval=0.1, max_iterations=1)

        # Verify job was completed and status in DB updated to APPROVED
        updated_record = self.store.get("rcpt_multi_proc_01")
        self.assertIsNotNone(updated_record)
        self.assertEqual(updated_record.status, ReceiptStatus.APPROVED)
        self.assertGreater(updated_record.total_amount, 0)
        self.assertEqual(self.queue.pending_count(), 0)

    def test_worker_retry_lifecycle_on_ocr_failure(self):
        """Validates that a failed OCR extraction retries up to max_retries before permanent failure."""
        class BrokenOCRAdapter:
            def extract_receipt(self, image_bytes, filename=""):
                raise RuntimeError("OCR Engine Timeout / Failure")

        self.storage.store_file("broken_scan.jpg", b"bad_image_data")
        record = ReceiptRecord(
            id="rcpt_retry_01",
            status=ReceiptStatus.QUEUED,
            image_storage_key="broken_scan.jpg"
        )
        self.store["rcpt_retry_01"] = record
        self.queue.enqueue("rcpt_retry_01")

        worker = ReceiptOCRWorker(
            queue_name="test_queue",
            ocr_provider=BrokenOCRAdapter(),
            storage_adapter=self.storage,
            store=self.store,
            queue=self.queue,
            max_retries=2
        )

        # Attempt 1: Fails -> re-queued (retry 1/2)
        worker.run_worker_loop(poll_interval=0.05, max_iterations=1)
        self.assertEqual(self.queue.get_retry_count("rcpt_retry_01"), 1)
        rec1 = self.store.get("rcpt_retry_01")
        self.assertEqual(rec1.status, ReceiptStatus.QUEUED)
        self.assertEqual(self.queue.pending_count(), 1)

        # Attempt 2: Fails -> re-queued (retry 2/2)
        worker.run_worker_loop(poll_interval=0.05, max_iterations=1)
        self.assertEqual(self.queue.get_retry_count("rcpt_retry_01"), 2)

        # Attempt 3: Exceeds max_retries=2 -> marked FAILED permanently
        worker.run_worker_loop(poll_interval=0.05, max_iterations=1)
        rec_final = self.store.get("rcpt_retry_01")
        self.assertEqual(rec_final.status, ReceiptStatus.FAILED)
        self.assertEqual(self.queue.pending_count(), 0)


if __name__ == "__main__":
    unittest.main()
