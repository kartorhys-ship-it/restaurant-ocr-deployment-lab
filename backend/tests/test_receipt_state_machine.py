"""Tests for Receipt Domain State Machine."""

import unittest
from backend.app.domain.receipt import (
    ReceiptStatus, ReceiptStateMachine, ReceiptStateTransitionError
)


class TestReceiptStateMachine(unittest.TestCase):
    def test_happy_path_transitions(self):
        # UPLOADED -> QUEUED
        s1 = ReceiptStateMachine.transition(ReceiptStatus.UPLOADED, ReceiptStatus.QUEUED)
        self.assertEqual(s1, ReceiptStatus.QUEUED)

        # QUEUED -> OCR_RUNNING
        s2 = ReceiptStateMachine.transition(s1, ReceiptStatus.OCR_RUNNING)
        self.assertEqual(s2, ReceiptStatus.OCR_RUNNING)

        # OCR_RUNNING -> PARSED
        s3 = ReceiptStateMachine.transition(s2, ReceiptStatus.PARSED)
        self.assertEqual(s3, ReceiptStatus.PARSED)

        # PARSED -> REVIEW_REQUIRED
        s4 = ReceiptStateMachine.transition(s3, ReceiptStatus.REVIEW_REQUIRED)
        self.assertEqual(s4, ReceiptStatus.REVIEW_REQUIRED)

        # REVIEW_REQUIRED -> APPROVED
        s5 = ReceiptStateMachine.transition(s4, ReceiptStatus.APPROVED)
        self.assertEqual(s5, ReceiptStatus.APPROVED)

    def test_illegal_transition_raises_error(self):
        # UPLOADED -> APPROVED directly must fail
        with self.assertRaises(ReceiptStateTransitionError):
            ReceiptStateMachine.transition(ReceiptStatus.UPLOADED, ReceiptStatus.APPROVED)

        # APPROVED is terminal, cannot transition back to QUEUED
        with self.assertRaises(ReceiptStateTransitionError):
            ReceiptStateMachine.transition(ReceiptStatus.APPROVED, ReceiptStatus.QUEUED)

    def test_failure_retry_path(self):
        # OCR_RUNNING -> FAILED
        s1 = ReceiptStateMachine.transition(ReceiptStatus.OCR_RUNNING, ReceiptStatus.FAILED)
        self.assertEqual(s1, ReceiptStatus.FAILED)

        # FAILED -> QUEUED (Retry)
        s2 = ReceiptStateMachine.transition(s1, ReceiptStatus.QUEUED)
        self.assertEqual(s2, ReceiptStatus.QUEUED)


if __name__ == "__main__":
    unittest.main()
