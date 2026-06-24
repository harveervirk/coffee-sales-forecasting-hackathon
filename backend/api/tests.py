import os
import tempfile
from unittest.mock import patch

import pandas as pd
from django.test import TestCase

from .services import (
    get_item_breakdown,
    get_location_breakdown,
    get_monthly_trends,
    get_province_breakdown,
    get_sales_summary,
)


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

FIXTURE_ROWS = [
    # TXN_001 has two line items; both rows share the same Transaction ID.
    {
        "Transaction ID": "TXN_001",
        "Item": "Coffee ",        # trailing space → normalises to "Coffee"
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
        "Item": "cookie",         # lowercase → normalises to "Cookie"
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
        # UNKNOWN date → NaT, UNKNOWN location, UNKNOWN payment
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
        # ERR_PM_102 payment; "Unknown" province → excluded from valid provinces
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

# Manually derived expected values for get_sales_summary:
#
#   total_revenue         = 7 + 2 + 3.5 + 12 + 3.5 = 28.0
#   total_quantity        = 2 + 1 + 1 + 3 + 1 = 8
#   unique_transactions   = 4  (TXN_001 counted once)
#   txn totals            = TXN_001:9, TXN_002:3.5, TXN_003:12, TXN_004:3.5
#   avg_txn_value         = round((9 + 3.5 + 12 + 3.5) / 4, 2) = 7.0
#   top_item              = "Coffee" (3 normalised rows)
#   top_province          = "British Columbia" (2 rows, "Unknown" excluded)
#   earliest_date         = "2023-01-01"
#   latest_date           = "2023-12-31"
#   invalid_date_count    = 1  ("UNKNOWN" → NaT)
#   unknown_payment       = 2  (UNKNOWN + ERR_PM_102)
#   unknown_location      = 1  (UNKNOWN)

EXPECTED_SUMMARY = {
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
    """Write FIXTURE_ROWS to a temporary .xlsx file and return its path."""
    df = pd.DataFrame(FIXTURE_ROWS)
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    df.to_excel(tmp.name, index=False)
    tmp.close()
    return tmp.name


class FixtureTestCase(TestCase):
    """Base class that creates a temporary fixture Excel once per test class."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fixture_path = _write_fixture_excel()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        os.unlink(cls.fixture_path)


# ---------------------------------------------------------------------------
# 1. get_sales_summary service tests
# ---------------------------------------------------------------------------

class GetSalesSummaryServiceTests(FixtureTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = get_sales_summary(cls.fixture_path)

    def test_total_revenue(self):
        self.assertEqual(self.result["total_revenue"], EXPECTED_SUMMARY["total_revenue"])

    def test_total_quantity(self):
        self.assertEqual(self.result["total_quantity"], EXPECTED_SUMMARY["total_quantity"])

    def test_unique_transactions(self):
        self.assertEqual(self.result["unique_transactions"], EXPECTED_SUMMARY["unique_transactions"])

    def test_average_transaction_value(self):
        self.assertEqual(self.result["average_transaction_value"], EXPECTED_SUMMARY["average_transaction_value"])

    def test_top_item_normalised(self):
        self.assertEqual(self.result["top_item"], EXPECTED_SUMMARY["top_item"])

    def test_top_province_excludes_unknown(self):
        self.assertEqual(self.result["top_province"], EXPECTED_SUMMARY["top_province"])

    def test_earliest_date(self):
        self.assertEqual(self.result["earliest_date"], EXPECTED_SUMMARY["earliest_date"])

    def test_latest_date(self):
        self.assertEqual(self.result["latest_date"], EXPECTED_SUMMARY["latest_date"])

    def test_invalid_date_count(self):
        self.assertEqual(self.result["invalid_date_count"], EXPECTED_SUMMARY["invalid_date_count"])

    def test_unknown_payment_method_count(self):
        self.assertEqual(self.result["unknown_payment_method_count"], EXPECTED_SUMMARY["unknown_payment_method_count"])

    def test_unknown_location_count(self):
        self.assertEqual(self.result["unknown_location_count"], EXPECTED_SUMMARY["unknown_location_count"])


# ---------------------------------------------------------------------------
# 2. get_monthly_trends service tests
#
# Fixture valid dates: 2023-01 (TXN_001 ×2 rows), 2023-06 (TXN_002), 2023-12 (TXN_004)
# TXN_003 has UNKNOWN date → excluded from trends.
#
# Expected months:
#   2023-01: revenue=9.0, quantity=3, unique_txns=1
#   2023-06: revenue=3.5, quantity=1, unique_txns=1
#   2023-12: revenue=3.5, quantity=1, unique_txns=1
# ---------------------------------------------------------------------------

class GetMonthlyTrendsServiceTests(FixtureTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = get_monthly_trends(cls.fixture_path)

    def test_returns_three_months(self):
        self.assertEqual(len(self.result), 3)

    def test_sorted_chronologically(self):
        months = [r["month"] for r in self.result]
        self.assertEqual(months, sorted(months))

    def test_first_month_is_january(self):
        self.assertEqual(self.result[0]["month"], "2023-01")

    def test_january_revenue(self):
        self.assertEqual(self.result[0]["total_revenue"], 9.0)

    def test_january_quantity(self):
        self.assertEqual(self.result[0]["total_quantity"], 3)

    def test_january_unique_transactions(self):
        # Both rows of TXN_001 fall in January → counts as 1 unique transaction
        self.assertEqual(self.result[0]["unique_transactions"], 1)

    def test_excludes_invalid_dates(self):
        # TXN_003 (UNKNOWN date) must not appear → only 3 unique transactions across all months
        total_txns = sum(r["unique_transactions"] for r in self.result)
        self.assertEqual(total_txns, 3)

    def test_values_are_python_types(self):
        r = self.result[0]
        self.assertIsInstance(r["total_revenue"], float)
        self.assertIsInstance(r["total_quantity"], int)
        self.assertIsInstance(r["unique_transactions"], int)


# ---------------------------------------------------------------------------
# 3. get_item_breakdown service tests
#
# Fixture items (normalised):
#   Coffee: rows TXN_001r1 + TXN_002 + TXN_004 → revenue=14.0, qty=4, txns=3
#   Tea:    TXN_003                              → revenue=12.0, qty=3, txns=1
#   Cookie: TXN_001r2                            → revenue=2.0,  qty=1, txns=1
# Sorted by revenue desc: Coffee, Tea, Cookie
# ---------------------------------------------------------------------------

class GetItemBreakdownServiceTests(FixtureTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = get_item_breakdown(cls.fixture_path)
        cls.by_item = {r["item"]: r for r in cls.result}

    def test_returns_three_items(self):
        self.assertEqual(len(self.result), 3)

    def test_sorted_by_revenue_descending(self):
        revenues = [r["total_revenue"] for r in self.result]
        self.assertEqual(revenues, sorted(revenues, reverse=True))

    def test_coffee_is_first(self):
        self.assertEqual(self.result[0]["item"], "Coffee")

    def test_coffee_revenue(self):
        self.assertEqual(self.by_item["Coffee"]["total_revenue"], 14.0)

    def test_coffee_quantity(self):
        self.assertEqual(self.by_item["Coffee"]["total_quantity"], 4)

    def test_coffee_unique_transactions(self):
        self.assertEqual(self.by_item["Coffee"]["unique_transactions"], 3)

    def test_item_names_are_normalised(self):
        # "Coffee " (space) and "coffee" both collapse into standard names
        self.assertIn("Coffee", self.by_item)
        self.assertIn("Cookie", self.by_item)


# ---------------------------------------------------------------------------
# 4. get_province_breakdown service tests
#
# Fixture valid provinces: British Columbia (TXN_001 ×2 rows), Manitoba (TXN_002),
# Saskatchewan (TXN_003). "Unknown" (TXN_004) must be excluded.
# Sorted by revenue desc: Saskatchewan(12.0), British Columbia(9.0), Manitoba(3.5)
# ---------------------------------------------------------------------------

class GetProvinceBreakdownServiceTests(FixtureTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = get_province_breakdown(cls.fixture_path)
        cls.by_province = {r["province"]: r for r in cls.result}

    def test_returns_three_provinces(self):
        self.assertEqual(len(self.result), 3)

    def test_excludes_unknown_province(self):
        self.assertNotIn("Unknown", self.by_province)

    def test_sorted_by_revenue_descending(self):
        revenues = [r["total_revenue"] for r in self.result]
        self.assertEqual(revenues, sorted(revenues, reverse=True))

    def test_saskatchewan_is_first(self):
        self.assertEqual(self.result[0]["province"], "Saskatchewan")

    def test_british_columbia_values(self):
        bc = self.by_province["British Columbia"]
        self.assertEqual(bc["total_revenue"], 9.0)
        self.assertEqual(bc["total_quantity"], 3)
        self.assertEqual(bc["unique_transactions"], 1)


# ---------------------------------------------------------------------------
# 5. get_location_breakdown service tests
#
# Fixture locations:
#   In-store: TXN_001r1 + TXN_001r2 + TXN_004 → revenue=12.5, qty=4, txns=2
#   UNKNOWN:  TXN_003                           → revenue=12.0, qty=3, txns=1
#   Takeaway: TXN_002                           → revenue=3.5,  qty=1, txns=1
# Sorted by revenue desc: In-store, UNKNOWN, Takeaway
# ---------------------------------------------------------------------------

class GetLocationBreakdownServiceTests(FixtureTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = get_location_breakdown(cls.fixture_path)
        cls.by_location = {r["location"]: r for r in cls.result}

    def test_returns_three_locations(self):
        self.assertEqual(len(self.result), 3)

    def test_includes_unknown_location(self):
        self.assertIn("UNKNOWN", self.by_location)

    def test_sorted_by_revenue_descending(self):
        revenues = [r["total_revenue"] for r in self.result]
        self.assertEqual(revenues, sorted(revenues, reverse=True))

    def test_in_store_is_first(self):
        self.assertEqual(self.result[0]["location"], "In-store")

    def test_in_store_values(self):
        instore = self.by_location["In-store"]
        self.assertEqual(instore["total_revenue"], 12.5)
        self.assertEqual(instore["total_quantity"], 4)
        self.assertEqual(instore["unique_transactions"], 2)


# ---------------------------------------------------------------------------
# 6–9. HTTP endpoint tests (service functions are mocked in all view tests)
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

MOCK_TRENDS = [
    {"month": "2023-01", "total_revenue": 7167.0, "total_quantity": 1726, "unique_transactions": 850},
    {"month": "2023-12", "total_revenue": 6852.0, "total_quantity": 1613, "unique_transactions": 814},
]

MOCK_ITEMS = [
    {"item": "Sandwich", "total_revenue": 20696.0, "total_quantity": 2587, "unique_transactions": 1303},
    {"item": "Coffee",   "total_revenue": 19320.0, "total_quantity": 5520, "unique_transactions": 2805},
]

MOCK_PROVINCES = [
    {"province": "British Columbia", "total_revenue": 28407.0, "total_quantity": 6582, "unique_transactions": 3281},
]

MOCK_LOCATIONS = [
    {"location": "In-store", "total_revenue": 50792.5, "total_quantity": 11788, "unique_transactions": 5902},
    {"location": "UNKNOWN",  "total_revenue": 7748.5,  "total_quantity": 1735,  "unique_transactions": 877},
]


class SalesSummaryViewTests(TestCase):

    def _get(self):
        with patch("api.views.get_sales_summary", return_value=MOCK_SUMMARY):
            return self.client.get("/api/sales/summary/")

    def test_returns_200(self):
        self.assertEqual(self._get().status_code, 200)

    def test_response_has_all_keys(self):
        self.assertEqual(set(self._get().json().keys()), set(MOCK_SUMMARY.keys()))

    def test_response_values_match_mock(self):
        data = self._get().json()
        for key, value in MOCK_SUMMARY.items():
            self.assertEqual(data[key], value, msg=f"Mismatch on key '{key}'")

    def test_post_returns_405(self):
        with patch("api.views.get_sales_summary", return_value=MOCK_SUMMARY):
            self.assertEqual(self.client.post("/api/sales/summary/").status_code, 405)


class SalesTrendsViewTests(TestCase):

    def _get(self):
        with patch("api.views.get_monthly_trends", return_value=MOCK_TRENDS):
            return self.client.get("/api/sales/trends/")

    def test_returns_200(self):
        self.assertEqual(self._get().status_code, 200)

    def test_response_is_list(self):
        self.assertIsInstance(self._get().json(), list)

    def test_items_have_expected_keys(self):
        keys = {"month", "total_revenue", "total_quantity", "unique_transactions"}
        self.assertEqual(set(self._get().json()[0].keys()), keys)

    def test_post_returns_405(self):
        with patch("api.views.get_monthly_trends", return_value=MOCK_TRENDS):
            self.assertEqual(self.client.post("/api/sales/trends/").status_code, 405)


class SalesItemsViewTests(TestCase):

    def _get(self):
        with patch("api.views.get_item_breakdown", return_value=MOCK_ITEMS):
            return self.client.get("/api/sales/items/")

    def test_returns_200(self):
        self.assertEqual(self._get().status_code, 200)

    def test_response_is_list(self):
        self.assertIsInstance(self._get().json(), list)

    def test_items_have_expected_keys(self):
        keys = {"item", "total_revenue", "total_quantity", "unique_transactions"}
        self.assertEqual(set(self._get().json()[0].keys()), keys)

    def test_post_returns_405(self):
        with patch("api.views.get_item_breakdown", return_value=MOCK_ITEMS):
            self.assertEqual(self.client.post("/api/sales/items/").status_code, 405)


class SalesProvincesViewTests(TestCase):

    def _get(self):
        with patch("api.views.get_province_breakdown", return_value=MOCK_PROVINCES):
            return self.client.get("/api/sales/provinces/")

    def test_returns_200(self):
        self.assertEqual(self._get().status_code, 200)

    def test_response_is_list(self):
        self.assertIsInstance(self._get().json(), list)

    def test_items_have_expected_keys(self):
        keys = {"province", "total_revenue", "total_quantity", "unique_transactions"}
        self.assertEqual(set(self._get().json()[0].keys()), keys)

    def test_post_returns_405(self):
        with patch("api.views.get_province_breakdown", return_value=MOCK_PROVINCES):
            self.assertEqual(self.client.post("/api/sales/provinces/").status_code, 405)


class SalesLocationsViewTests(TestCase):

    def _get(self):
        with patch("api.views.get_location_breakdown", return_value=MOCK_LOCATIONS):
            return self.client.get("/api/sales/locations/")

    def test_returns_200(self):
        self.assertEqual(self._get().status_code, 200)

    def test_response_is_list(self):
        self.assertIsInstance(self._get().json(), list)

    def test_items_have_expected_keys(self):
        keys = {"location", "total_revenue", "total_quantity", "unique_transactions"}
        self.assertEqual(set(self._get().json()[0].keys()), keys)

    def test_post_returns_405(self):
        with patch("api.views.get_location_breakdown", return_value=MOCK_LOCATIONS):
            self.assertEqual(self.client.post("/api/sales/locations/").status_code, 405)


# ---------------------------------------------------------------------------
# 10. Health endpoint (unchanged)
# ---------------------------------------------------------------------------

class HealthEndpointTests(TestCase):

    def test_health_returns_200(self):
        self.assertEqual(self.client.get('/api/health/').status_code, 200)

    def test_health_returns_ok_json(self):
        self.assertJSONEqual(self.client.get('/api/health/').content, {'status': 'ok'})
