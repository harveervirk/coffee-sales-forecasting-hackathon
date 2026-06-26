import os
import shutil
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd
from django.test import TestCase

from .forecasting import (
    aggregate_monthly,
    calc_forecast_bounds,
    calc_mae,
    calc_mape,
    calc_rmse,
    generate_recommendations,
    load_daily_sales,
    read_forecast_csv,
    read_metrics_csv,
    seasonal_naive_predict,
    select_best_model,
    split_train_test,
)
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


# ===========================================================================
# Forecasting function unit tests
# ===========================================================================

# ---------------------------------------------------------------------------
# Minimal synthetic Excel fixture for load_daily_sales tests
# (reuses FIXTURE_ROWS / _write_fixture_excel from above)
# ---------------------------------------------------------------------------

class LoadDailySalesTests(FixtureTestCase):
    """Tests 1–3: data preparation, invalid-date exclusion, gap-filling."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.daily = load_daily_sales(cls.fixture_path)

    def test_returns_series(self):
        self.assertIsInstance(self.daily, pd.Series)

    def test_invalid_dates_excluded(self):
        # FIXTURE_ROWS has TXN_003 with "UNKNOWN" date → row must be excluded.
        # Valid revenues: 7.0 + 2.0 + 3.5 + 3.5 = 16.0
        self.assertAlmostEqual(float(self.daily.sum()), 16.0)

    def test_fills_missing_calendar_dates_with_zero(self):
        # Fixture spans 2023-01-01 → 2023-12-31 (365 days).
        # Valid dates: Jan 1, Jan 2, Jun 15, Dec 31.
        # All other days must be 0.
        self.assertEqual(len(self.daily), 365)
        jan3_value = float(self.daily["2023-01-03"])
        self.assertEqual(jan3_value, 0.0)

    def test_index_is_contiguous(self):
        expected = pd.date_range(self.daily.index.min(), self.daily.index.max(), freq="D")
        self.assertEqual(len(self.daily), len(expected))


# ---------------------------------------------------------------------------
# Test 4: seasonal naive
# ---------------------------------------------------------------------------

class SeasonalNaivePredictTests(TestCase):

    def _make_series(self, values):
        dates = pd.date_range("2023-01-01", periods=len(values), freq="D")
        return pd.Series(values, index=dates, name="actual_revenue", dtype=float)

    def test_repeats_weekly_pattern(self):
        # train ends with the pattern [1,2,3,4,5,6,7] in the last 7 days
        train = self._make_series(list(range(1, 22)))  # 21 values; last 7 = [15,16,17,18,19,20,21]
        preds = seasonal_naive_predict(train, 7)
        expected = np.array([15, 16, 17, 18, 19, 20, 21], dtype=float)
        np.testing.assert_array_equal(preds, expected)

    def test_output_length_matches_steps(self):
        train = self._make_series([10.0] * 14)
        preds = seasonal_naive_predict(train, 14)
        self.assertEqual(len(preds), 14)

    def test_returns_numpy_array(self):
        train = self._make_series([5.0] * 7)
        self.assertIsInstance(seasonal_naive_predict(train, 3), np.ndarray)


# ---------------------------------------------------------------------------
# Tests 5–7: metric calculations
# ---------------------------------------------------------------------------

class MetricCalculationTests(TestCase):

    def test_mae_correct(self):
        actual    = np.array([10.0, 20.0, 30.0])
        predicted = np.array([12.0, 18.0, 33.0])
        # |10-12| + |20-18| + |30-33| = 2+2+3 = 7 → mean = 7/3 ≈ 2.333
        self.assertAlmostEqual(calc_mae(actual, predicted), 7 / 3, places=5)

    def test_rmse_correct(self):
        actual    = np.array([0.0, 10.0])
        predicted = np.array([0.0, 16.0])
        # sqrt(((0)^2 + (6)^2) / 2) = sqrt(18) ≈ 4.2426
        self.assertAlmostEqual(calc_rmse(actual, predicted), np.sqrt(18), places=5)

    def test_mape_skips_zero_actuals(self):
        # Row with actual=0 must be ignored so no ZeroDivisionError
        actual    = np.array([0.0, 10.0])
        predicted = np.array([5.0, 12.0])
        # Only the second row counts: |10-12|/10 * 100 = 20%
        result = calc_mape(actual, predicted)
        self.assertAlmostEqual(result, 20.0, places=5)

    def test_mape_all_zeros_returns_nan(self):
        actual    = np.array([0.0, 0.0])
        predicted = np.array([5.0, 5.0])
        result = calc_mape(actual, predicted)
        self.assertTrue(np.isnan(result))

    def test_mae_zero_when_perfect(self):
        arr = np.array([1.0, 2.0, 3.0])
        self.assertEqual(calc_mae(arr, arr), 0.0)


# ---------------------------------------------------------------------------
# Test 8: negative forecasts clipped to zero
# ---------------------------------------------------------------------------

class ForecastBoundsClippingTests(TestCase):

    def test_lower_bound_clipped_to_zero(self):
        # Residual std large enough to push lower bound negative
        forecast  = np.array([10.0, 5.0, 2.0])
        residuals = np.array([100.0, 100.0, 100.0])  # std ≈ 0; margin = 1.96 * 0 = 0
        # Use residuals with high variance instead
        residuals = np.arange(1, 201, dtype=float)   # std ≈ 57.7; margin ≈ 113
        lower, upper = calc_forecast_bounds(residuals, forecast)
        self.assertTrue(np.all(lower >= 0), "All lower bounds must be ≥ 0")

    def test_upper_bound_not_clipped(self):
        forecast  = np.array([100.0])
        residuals = np.array([1.0, 2.0, 3.0])
        lower, upper = calc_forecast_bounds(residuals, forecast)
        self.assertGreater(upper[0], forecast[0])


# ---------------------------------------------------------------------------
# Test 9: best model selection
# ---------------------------------------------------------------------------

class SelectBestModelTests(TestCase):

    def test_selects_model_with_lowest_mae(self):
        metrics = [
            {"model": "Seasonal Naive", "mae": 58.92, "selected": False},
            {"model": "Holt-Winters",   "mae": 43.96, "selected": True},
        ]
        self.assertEqual(select_best_model(metrics), "Holt-Winters")

    def test_works_when_naive_wins(self):
        metrics = [
            {"model": "Holt-Winters",   "mae": 80.0, "selected": False},
            {"model": "Seasonal Naive", "mae": 30.0, "selected": True},
        ]
        self.assertEqual(select_best_model(metrics), "Seasonal Naive")


# ---------------------------------------------------------------------------
# Test 10: monthly aggregation
# ---------------------------------------------------------------------------

class AggregateMonthlyTests(TestCase):

    def test_groups_by_calendar_month(self):
        # 3 days: Jan 30, Jan 31, Feb 1
        dates    = pd.DatetimeIndex(["2024-01-30", "2024-01-31", "2024-02-01"])
        forecast = np.array([100.0, 200.0, 150.0])
        lower    = np.array([80.0,  180.0, 130.0])
        upper    = np.array([120.0, 220.0, 170.0])

        result = aggregate_monthly(dates, forecast, lower, upper)
        self.assertEqual(len(result), 2)

        jan = next(r for r in result if r["month"] == "2024-01")
        feb = next(r for r in result if r["month"] == "2024-02")

        self.assertAlmostEqual(jan["forecast_revenue"], 300.0)
        self.assertAlmostEqual(feb["forecast_revenue"], 150.0)

    def test_sorted_chronologically(self):
        dates    = pd.DatetimeIndex(["2024-03-01", "2024-01-15"])
        forecast = np.array([50.0, 60.0])
        lower    = np.array([40.0, 50.0])
        upper    = np.array([60.0, 70.0])
        result   = aggregate_monthly(dates, forecast, lower, upper)
        months   = [r["month"] for r in result]
        self.assertEqual(months, sorted(months))

    def test_returns_python_float_types(self):
        dates    = pd.DatetimeIndex(["2024-01-01"])
        forecast = np.array([123.4])
        lower    = np.array([100.0])
        upper    = np.array([150.0])
        result   = aggregate_monthly(dates, forecast, lower, upper)
        self.assertIsInstance(result[0]["forecast_revenue"], float)


# ---------------------------------------------------------------------------
# Test 11: forecast output file creation (round-trip write + read)
# ---------------------------------------------------------------------------

class ForecastOutputFileTests(TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    def _write_mock_files(self):
        pd.DataFrame([{
            "selected_model":           "Holt-Winters",
            "forecast_start_date":      "2024-01-01",
            "forecast_end_date":        "2024-06-30",
            "historical_total_revenue": 84327.0,
            "forecast_total_revenue":   44000.0,
            "expected_growth_percent":  2.5,
            "best_model_mae":           43.96,
            "best_model_rmse":          57.13,
            "best_model_mape":          24.49,
        }]).to_csv(f"{self.tmp_dir}/forecast_summary.csv", index=False)

        pd.DataFrame([
            {"month": "2024-01", "forecast_revenue": 7500.0, "lower_bound": 6000.0, "upper_bound": 9000.0},
            {"month": "2024-02", "forecast_revenue": 7000.0, "lower_bound": 5500.0, "upper_bound": 8500.0},
        ]).to_csv(f"{self.tmp_dir}/monthly_sales_forecast.csv", index=False)

        pd.DataFrame([
            {"model": "Holt-Winters",   "mae": 43.96, "rmse": 57.13, "mape": 24.49, "selected": True},
            {"model": "Seasonal Naive", "mae": 58.92, "rmse": 71.75, "mape": 35.51, "selected": False},
        ]).to_csv(f"{self.tmp_dir}/model_metrics.csv", index=False)

    def test_read_forecast_csv_has_required_keys(self):
        self._write_mock_files()
        data = read_forecast_csv(self.tmp_dir)
        required = {
            "selected_model", "forecast_start_date", "forecast_end_date",
            "historical_total_revenue", "forecast_total_revenue",
            "expected_growth_percent", "best_model_mae", "best_model_rmse",
            "best_model_mape", "monthly_forecast",
        }
        self.assertEqual(set(data.keys()), required)

    def test_read_forecast_csv_monthly_forecast_is_list(self):
        self._write_mock_files()
        data = read_forecast_csv(self.tmp_dir)
        self.assertIsInstance(data["monthly_forecast"], list)
        self.assertEqual(len(data["monthly_forecast"]), 2)

    def test_read_metrics_csv_has_models_key(self):
        self._write_mock_files()
        data = read_metrics_csv(self.tmp_dir)
        self.assertIn("models", data)
        self.assertEqual(len(data["models"]), 2)

    def test_read_forecast_csv_raises_when_missing(self):
        with self.assertRaises(FileNotFoundError):
            read_forecast_csv(self.tmp_dir)   # files not written yet

    def test_read_metrics_csv_raises_when_missing(self):
        with self.assertRaises(FileNotFoundError):
            read_metrics_csv(self.tmp_dir)


# ===========================================================================
# Forecast HTTP endpoint tests  (tests 12–19)
# ===========================================================================

MOCK_FORECAST_DATA = {
    "selected_model":           "Holt-Winters",
    "forecast_start_date":      "2024-01-01",
    "forecast_end_date":        "2024-06-30",
    "historical_total_revenue": 84327.0,
    "forecast_total_revenue":   44000.0,
    "expected_growth_percent":  2.5,
    "best_model_mae":           43.96,
    "best_model_rmse":          57.13,
    "best_model_mape":          24.49,
    "monthly_forecast": [
        {"month": "2024-01", "forecast_revenue": 7500.0, "lower_bound": 6000.0, "upper_bound": 9000.0},
        {"month": "2024-02", "forecast_revenue": 6800.0, "lower_bound": 5300.0, "upper_bound": 8300.0},
    ],
}

MOCK_METRICS_DATA = {
    "models": [
        {"model": "Holt-Winters",   "mae": 43.96, "rmse": 57.13, "mape": 24.49, "selected": True},
        {"model": "Seasonal Naive", "mae": 58.92, "rmse": 71.75, "mape": 35.51, "selected": False},
    ]
}

FORECAST_ENDPOINT_KEYS = {
    "selected_model", "forecast_start_date", "forecast_end_date",
    "forecast_total_revenue", "expected_growth_percent", "monthly_forecast",
}
MONTHLY_ITEM_KEYS = {"month", "forecast_revenue", "lower_bound", "upper_bound"}


# --- Tests 12–13 + 18–19 for /api/forecast/ ---

class ForecastViewTests(TestCase):

    def _get(self):
        with patch("api.views.read_forecast_csv", return_value=MOCK_FORECAST_DATA):
            return self.client.get("/api/forecast/")

    def test_returns_200(self):   # test 12
        self.assertEqual(self._get().status_code, 200)

    def test_response_shape(self):   # test 13
        data = self._get().json()
        self.assertEqual(set(data.keys()), FORECAST_ENDPOINT_KEYS)
        self.assertIsInstance(data["monthly_forecast"], list)
        self.assertGreater(len(data["monthly_forecast"]), 0)
        self.assertEqual(set(data["monthly_forecast"][0].keys()), MONTHLY_ITEM_KEYS)

    def test_post_returns_405(self):   # test 18
        with patch("api.views.read_forecast_csv", return_value=MOCK_FORECAST_DATA):
            self.assertEqual(self.client.post("/api/forecast/").status_code, 405)

    def test_missing_files_returns_503(self):   # test 19
        with patch("api.views.read_forecast_csv", side_effect=FileNotFoundError):
            response = self.client.get("/api/forecast/")
        self.assertEqual(response.status_code, 503)
        self.assertIn("error", response.json())


# --- Tests 14–15 + 18–19 for /api/forecast/metrics/ ---

class ForecastMetricsViewTests(TestCase):

    def _get(self):
        with patch("api.views.read_metrics_csv", return_value=MOCK_METRICS_DATA):
            return self.client.get("/api/forecast/metrics/")

    def test_returns_200(self):   # test 14
        self.assertEqual(self._get().status_code, 200)

    def test_response_shape(self):   # test 15
        data = self._get().json()
        self.assertIn("models", data)
        self.assertIsInstance(data["models"], list)
        item = data["models"][0]
        for key in ("model", "mae", "rmse", "mape", "selected"):
            self.assertIn(key, item)

    def test_post_returns_405(self):   # test 18
        with patch("api.views.read_metrics_csv", return_value=MOCK_METRICS_DATA):
            self.assertEqual(self.client.post("/api/forecast/metrics/").status_code, 405)

    def test_missing_files_returns_503(self):   # test 19
        with patch("api.views.read_metrics_csv", side_effect=FileNotFoundError):
            response = self.client.get("/api/forecast/metrics/")
        self.assertEqual(response.status_code, 503)
        self.assertIn("error", response.json())


# --- Tests 16–19 for /api/recommendations/ ---

class RecommendationsViewTests(TestCase):

    def _get(self):
        with patch("api.views.read_forecast_csv", return_value=MOCK_FORECAST_DATA):
            return self.client.get("/api/recommendations/")

    def test_returns_200(self):   # test 16
        self.assertEqual(self._get().status_code, 200)

    def test_response_has_recommendations_list(self):
        data = self._get().json()
        self.assertIn("recommendations", data)
        self.assertIsInstance(data["recommendations"], list)
        self.assertGreater(len(data["recommendations"]), 0)

    def test_recommendation_items_have_required_fields(self):
        recs = self._get().json()["recommendations"]
        for rec in recs:
            for field in ("priority", "title", "message", "evidence"):
                self.assertIn(field, rec, msg=f"Missing field '{field}' in {rec}")

    def test_post_returns_405(self):   # test 18
        with patch("api.views.read_forecast_csv", return_value=MOCK_FORECAST_DATA):
            self.assertEqual(self.client.post("/api/recommendations/").status_code, 405)

    def test_missing_files_returns_503(self):   # test 19
        with patch("api.views.read_forecast_csv", side_effect=FileNotFoundError):
            response = self.client.get("/api/recommendations/")
        self.assertEqual(response.status_code, 503)
        self.assertIn("error", response.json())


# --- Test 17: recommendations derived from supplied values ---

class GenerateRecommendationsTests(TestCase):

    def _make_data(self, growth: float, monthly=None):
        if monthly is None:
            monthly = MOCK_FORECAST_DATA["monthly_forecast"]
        return {
            **MOCK_FORECAST_DATA,
            "expected_growth_percent": growth,
            "monthly_forecast": monthly,
        }

    def test_positive_growth_gives_growth_recommendation(self):
        recs = generate_recommendations(self._make_data(5.0))["recommendations"]
        self.assertIn("growth", recs[0]["title"].lower())

    def test_negative_growth_gives_decline_recommendation(self):
        recs = generate_recommendations(self._make_data(-3.0))["recommendations"]
        self.assertIn("decline", recs[0]["title"].lower())

    def test_peak_month_identified_correctly(self):
        # Jan has higher revenue than Feb in MOCK_FORECAST_DATA
        recs = generate_recommendations(self._make_data(2.5))["recommendations"]
        peak_rec = next(r for r in recs if "peak" in r["title"].lower())
        self.assertIn("2024-01", peak_rec["title"])

    def test_lowest_month_identified_correctly(self):
        recs = generate_recommendations(self._make_data(2.5))["recommendations"]
        low_rec = next(r for r in recs if "promotion" in r["title"].lower() or "lowest" in r["title"].lower())
        self.assertIn("2024-02", low_rec["title"])

    def test_evidence_mentions_growth_total(self):
        data = self._make_data(2.5)
        recs = generate_recommendations(data)["recommendations"]
        # First recommendation's evidence must reference the forecast total
        self.assertIn("44,000", recs[0]["evidence"])


# ===========================================================================
# Portal page tests
# ===========================================================================

class PortalPageTests(TestCase):
    """Tests that every portal page responds correctly."""

    # --- 1–5: each page returns 200 ---

    def test_overview_returns_200(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_analytics_returns_200(self):
        response = self.client.get('/analytics/')
        self.assertEqual(response.status_code, 200)

    def test_forecast_centre_returns_200(self):
        response = self.client.get('/forecast-centre/')
        self.assertEqual(response.status_code, 200)

    def test_recommendations_page_returns_200(self):
        response = self.client.get('/recommendations/')
        self.assertEqual(response.status_code, 200)

    def test_data_quality_returns_200(self):
        response = self.client.get('/data-quality/')
        self.assertEqual(response.status_code, 200)

    # --- 6: correct templates used ---

    def test_overview_uses_correct_template(self):
        response = self.client.get('/')
        self.assertTemplateUsed(response, 'api/overview.html')
        self.assertTemplateUsed(response, 'api/base.html')

    def test_analytics_uses_correct_template(self):
        response = self.client.get('/analytics/')
        self.assertTemplateUsed(response, 'api/analytics.html')
        self.assertTemplateUsed(response, 'api/base.html')

    def test_forecast_centre_uses_correct_template(self):
        response = self.client.get('/forecast-centre/')
        self.assertTemplateUsed(response, 'api/forecast_centre.html')
        self.assertTemplateUsed(response, 'api/base.html')

    def test_recommendations_page_uses_correct_template(self):
        response = self.client.get('/recommendations/')
        self.assertTemplateUsed(response, 'api/recommendations.html')
        self.assertTemplateUsed(response, 'api/base.html')

    def test_data_quality_uses_correct_template(self):
        response = self.client.get('/data-quality/')
        self.assertTemplateUsed(response, 'api/data_quality.html')
        self.assertTemplateUsed(response, 'api/base.html')

    # --- 7: navigation links present ---

    def test_navigation_links_present_on_overview(self):
        content = self.client.get('/').content.decode()
        self.assertIn('/analytics/', content)
        self.assertIn('/forecast-centre/', content)
        self.assertIn('/recommendations/', content)
        self.assertIn('/data-quality/', content)

    def test_navigation_links_present_on_analytics(self):
        content = self.client.get('/analytics/').content.decode()
        self.assertIn('href="/"', content)
        self.assertIn('/forecast-centre/', content)
        self.assertIn('/recommendations/', content)

    # --- 8: existing API routes still work ---

    def test_health_api_still_returns_200(self):
        self.assertEqual(self.client.get('/api/health/').status_code, 200)

    def test_sales_summary_api_still_reachable(self):
        # The real file may not exist in CI; we only check the URL resolves
        # (it will return 500 if the Excel is missing, but not 404)
        status = self.client.get('/api/sales/summary/').status_code
        self.assertIn(status, [200, 500])

    def test_forecast_api_url_resolves(self):
        status = self.client.get('/api/forecast/').status_code
        self.assertIn(status, [200, 503])

    def test_recommendations_api_url_resolves(self):
        status = self.client.get('/api/recommendations/').status_code
        self.assertIn(status, [200, 503])

    # --- 9: static file references in HTML ---

    def test_overview_references_dashboard_css(self):
        content = self.client.get('/').content.decode()
        self.assertIn('dashboard.css', content)

    def test_overview_references_common_js(self):
        content = self.client.get('/').content.decode()
        self.assertIn('common.js', content)

    def test_overview_references_page_js(self):
        content = self.client.get('/').content.decode()
        self.assertIn('overview.js', content)

    def test_analytics_references_page_js(self):
        content = self.client.get('/analytics/').content.decode()
        self.assertIn('analytics.js', content)

    def test_forecast_centre_references_page_js(self):
        content = self.client.get('/forecast-centre/').content.decode()
        self.assertIn('forecast.js', content)

    def test_recommendations_page_references_page_js(self):
        content = self.client.get('/recommendations/').content.decode()
        self.assertIn('recommendations.js', content)

    def test_data_quality_references_page_js(self):
        content = self.client.get('/data-quality/').content.decode()
        self.assertIn('data_quality.js', content)

    # --- Active page highlighting ---

    def test_overview_marks_overview_nav_active(self):
        content = self.client.get('/').content.decode()
        # The overview nav link should carry the 'active' class
        self.assertIn('nav-link active', content)

    def test_analytics_marks_analytics_nav_active(self):
        content = self.client.get('/analytics/').content.decode()
        self.assertIn('nav-link active', content)

    # --- Accessibility: semantic landmarks ---

    def test_overview_has_main_landmark(self):
        content = self.client.get('/').content.decode()
        self.assertIn('role="main"', content)

    def test_overview_has_nav_landmark(self):
        content = self.client.get('/').content.decode()
        self.assertIn('aria-label="Main navigation"', content)

    def test_overview_has_h1(self):
        content = self.client.get('/').content.decode()
        self.assertIn('<h1>', content)

    # --- Scenario Lab ---

    def test_scenario_lab_returns_200(self):
        response = self.client.get('/scenario-lab/')
        self.assertEqual(response.status_code, 200)

    def test_scenario_lab_uses_correct_template(self):
        response = self.client.get('/scenario-lab/')
        self.assertTemplateUsed(response, 'api/scenario_lab.html')
        self.assertTemplateUsed(response, 'api/base.html')

    def test_scenario_lab_references_scenario_js(self):
        content = self.client.get('/scenario-lab/').content.decode()
        self.assertIn('scenario_page.js', content)
        self.assertIn('scenario.js', content)

    def test_scenario_lab_in_navigation(self):
        content = self.client.get('/').content.decode()
        self.assertIn('/scenario-lab/', content)

    def test_scenario_lab_has_sliders(self):
        content = self.client.get('/scenario-lab/').content.decode()
        self.assertIn('s-traffic', content)
        self.assertIn('s-price', content)
        self.assertIn('s-discount', content)

    # --- Verify Ask CanAI and Presentation Mode have been removed ---

    def test_ask_canai_removed_from_base(self):
        """Ask CanAI panel and button must not exist after simplification."""
        content = self.client.get('/').content.decode()
        self.assertNotIn('openCanAI', content)
        self.assertNotIn('canai-panel', content)

    def test_presentation_mode_removed_from_base(self):
        """Presentation Mode toggle and logic must not exist after simplification."""
        content = self.client.get('/').content.decode()
        self.assertNotIn('togglePresentationMode', content)
        self.assertNotIn('pres-toggle', content)

    def test_services_js_referenced(self):
        content = self.client.get('/').content.decode()
        self.assertIn('services.js', content)

    def test_scenario_js_loaded_in_base(self):
        content = self.client.get('/').content.decode()
        self.assertIn('scenario.js', content)
