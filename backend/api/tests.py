import os
import tempfile
from unittest.mock import patch

import pandas as pd
from django.test import TestCase

from .services import get_sales_summary


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FIXTURE_ROWS = [
    # TXN_001 appears twice — same transaction, two line items
    {
        "Transaction ID": "TXN_001",
        "Item": "Coffee ",        # trailing space — should normalise to "Coffee"
        "Quantity": 2,
        "Price Per Unit": 3.5,
        "Total Spent": 7.0,
        "Payment Method": "Cash",
        "Location": "In-store",
        "Transaction Date": "2023-01-01",
        "Province": "British Columbia",
    },
    {
        "Transaction ID": "TXN_001",
        "Item": "cookie",         # lowercase — should normalise to "Cookie"
        "Quantity": 1,
        "Price Per Unit": 2.0,
        "Total Spent": 2.0,
        "Payment Method": "Cash",
        "Location": "In-store",
        "Transaction Date": "2023-01-02",
        "Province": "British Columbia",
    },
    {
        "Transaction ID": "TXN_002",
        "Item": "Coffee",
        "Quantity": 1,
        "Price Per Unit": 3.5,
        "Total Spent": 3.5,
        "Payment Method": "Credit Card",
        "Location": "Takeaway",
        "Transaction Date": "2023-06-15",
        "Province": "Manitoba",
    },
    {
        # UNKNOWN date, UNKNOWN location, UNKNOWN payment → all three quality counters
        "Transaction ID": "TXN_003",
        "Item": "Tea",
        "Quantity": 3,
        "Price Per Unit": 4.0,
        "Total Spent": 12.0,
        "Payment Method": "UNKNOWN",
        "Location": "UNKNOWN",
        "Transaction Date": "UNKNOWN",
        "Province": "Saskatchewan",
    },
    {
        # ERR_PM_102 payment, Unknown province (excluded from top_province)
        "Transaction ID": "TXN_004",
        "Item": "Coffee",
        "Quantity": 1,
        "Price Per Unit": 3.5,
        "Total Spent": 3.5,
        "Payment Method": "ERR_PM_102",
        "Location": "In-store",
        "Transaction Date": "2023-12-31",
        "Province": "Unknown",
    },
]

# Expected values derived manually from FIXTURE_ROWS:
#   total_revenue       = 7 + 2 + 3.5 + 12 + 3.5 = 28.0
#   total_quantity      = 2 + 1 + 1 + 3 + 1 = 8
#   unique_transactions = 4  (TXN_001 counted once)
#   txn totals          = TXN_001: 9, TXN_002: 3.5, TXN_003: 12, TXN_004: 3.5
#   avg_txn_value       = round((9 + 3.5 + 12 + 3.5) / 4, 2) = 7.0
#   top_item            = "Coffee" (3 normalised rows vs Tea 1, Cookie 1)
#   top_province        = "British Columbia" (2 rows) — "Unknown" excluded
#   earliest_date       = "2023-01-01"
#   latest_date         = "2023-12-31"
#   invalid_date_count  = 1  ("UNKNOWN" coerces to NaT)
#   unknown_payment     = 2  (UNKNOWN + ERR_PM_102)
#   unknown_location    = 1  (UNKNOWN)

EXPECTED = {
    "total_revenue": 28.0,
    "total_quantity": 8,
    "unique_transactions": 4,
    "average_transaction_value": 7.0,
    "top_item": "Coffee",
    "top_province": "British Columbia",
    "earliest_date": "2023-01-01",
    "latest_date": "2023-12-31",
    "invalid_date_count": 1,
    "unknown_payment_method_count": 2,
    "unknown_location_count": 1,
}


def _write_fixture_excel() -> str:
    """Write FIXTURE_ROWS to a temporary .xlsx file and return the path."""
    df = pd.DataFrame(FIXTURE_ROWS)
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    df.to_excel(tmp.name, index=False)
    tmp.close()
    return tmp.name


# ---------------------------------------------------------------------------
# 1. Service unit tests
# ---------------------------------------------------------------------------

class GetSalesSummaryServiceTests(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fixture_path = _write_fixture_excel()
        cls.result = get_sales_summary(cls.fixture_path)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        os.unlink(cls.fixture_path)

    def test_total_revenue(self):
        self.assertEqual(self.result["total_revenue"], EXPECTED["total_revenue"])

    def test_total_quantity(self):
        self.assertEqual(self.result["total_quantity"], EXPECTED["total_quantity"])

    def test_unique_transactions(self):
        self.assertEqual(self.result["unique_transactions"], EXPECTED["unique_transactions"])

    def test_average_transaction_value(self):
        self.assertEqual(
            self.result["average_transaction_value"],
            EXPECTED["average_transaction_value"],
        )

    def test_top_item_normalised(self):
        self.assertEqual(self.result["top_item"], EXPECTED["top_item"])

    def test_top_province_excludes_unknown(self):
        self.assertEqual(self.result["top_province"], EXPECTED["top_province"])

    def test_earliest_date(self):
        self.assertEqual(self.result["earliest_date"], EXPECTED["earliest_date"])

    def test_latest_date(self):
        self.assertEqual(self.result["latest_date"], EXPECTED["latest_date"])

    def test_invalid_date_count(self):
        self.assertEqual(self.result["invalid_date_count"], EXPECTED["invalid_date_count"])

    def test_unknown_payment_method_count(self):
        self.assertEqual(
            self.result["unknown_payment_method_count"],
            EXPECTED["unknown_payment_method_count"],
        )

    def test_unknown_location_count(self):
        self.assertEqual(
            self.result["unknown_location_count"],
            EXPECTED["unknown_location_count"],
        )


# ---------------------------------------------------------------------------
# 2. HTTP endpoint tests  (service is mocked — tests the Django layer only)
# ---------------------------------------------------------------------------

MOCK_SUMMARY = {
    "total_revenue": 86288.0,
    "total_quantity": 19853,
    "unique_transactions": 9956,
    "average_transaction_value": 8.67,
    "top_item": "Coffee",
    "top_province": "British Columbia",
    "earliest_date": "2023-01-01",
    "latest_date": "2023-12-31",
    "invalid_date_count": 240,
    "unknown_payment_method_count": 555,
    "unknown_location_count": 878,
}

EXPECTED_KEYS = set(MOCK_SUMMARY.keys())


class SalesSummaryViewTests(TestCase):

    def _get(self):
        with patch("api.views.get_sales_summary", return_value=MOCK_SUMMARY):
            return self.client.get("/api/sales/summary/")

    def test_returns_200(self):
        self.assertEqual(self._get().status_code, 200)

    def test_response_has_all_keys(self):
        data = self._get().json()
        self.assertEqual(set(data.keys()), EXPECTED_KEYS)

    def test_response_values_match_mock(self):
        data = self._get().json()
        for key, value in MOCK_SUMMARY.items():
            self.assertEqual(data[key], value, msg=f"Mismatch on key '{key}'")

    def test_post_returns_405(self):
        with patch("api.views.get_sales_summary", return_value=MOCK_SUMMARY):
            response = self.client.post("/api/sales/summary/")
        self.assertEqual(response.status_code, 405)


# ---------------------------------------------------------------------------
# 3. Existing health endpoint tests
# ---------------------------------------------------------------------------

class HealthEndpointTests(TestCase):

    def test_health_returns_200(self):
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 200)

    def test_health_returns_ok_json(self):
        response = self.client.get('/api/health/')
        self.assertJSONEqual(response.content, {'status': 'ok'})
