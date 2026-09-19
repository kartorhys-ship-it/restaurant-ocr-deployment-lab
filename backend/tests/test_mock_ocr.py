"""Tests for Mock OCR Adapter."""

import unittest
from backend.app.integrations.ocr.mock_adapter import MockOCRAdapter


class TestMockOCRAdapter(unittest.TestCase):
    def setUp(self):
        self.adapter = MockOCRAdapter(default_confidence=0.95)

    def test_mock_ocr_extracts_structured_data(self):
        result = self.adapter.extract_receipt(b"fake_image_bytes", filename="invoice.jpg")
        self.assertEqual(result.supplier_name, "Siam Fresh Wholesale Ltd.")
        self.assertEqual(result.currency, "THB")
        self.assertEqual(result.confidence_score, 0.95)
        self.assertGreater(len(result.lines), 0)
        self.assertEqual(result.total_amount, sum(line.total_price for line in result.lines))


if __name__ == "__main__":
    unittest.main()
