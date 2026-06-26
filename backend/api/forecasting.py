"""
Forecasting utilities for coffee sales.

All functions are pure Python / NumPy / pandas with no Django imports,
making them independently testable.

IMPORTANT – confidence bounds:
    lower_bound = forecast - 1.96 * residual_std
    upper_bound = forecast + 1.96 * residual_std
These are approximate uncertainty ranges derived from holdout residual
standard deviation. They are NOT formal statistical confidence intervals.
"""
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def load_daily_sales(filepath: str) -> pd.Series:
    """
    Load the source Excel file, drop rows with unparseable Transaction Dates,
    aggregate Total Spent by calendar day, and fill any missing days with 0.

    Returns a pd.Series named "actual_revenue" with a DatetimeIndex.
    """
    df = pd.read_excel(filepath)
    df["parsed_date"] = pd.to_datetime(df["Transaction Date"], errors="coerce")
    valid = df[df["parsed_date"].notna()].copy()

    daily = valid.groupby("parsed_date")["Total Spent"].sum()
    full_range = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(full_range, fill_value=0.0)
    daily.name = "actual_revenue"
    return daily


def split_train_test(daily: pd.Series, test_days: int = 60):
    """
    Time-based holdout split.  Never uses random shuffling.
    Returns (train, test) where test is the final test_days of the series.
    """
    train = daily.iloc[:-test_days]
    test  = daily.iloc[-test_days:]
    return train, test


def get_forecast_period(last_date: pd.Timestamp):
    """
    Return (forecast_start, forecast_end).
    forecast_end is the last calendar day of the sixth future month
    counting from forecast_start.

    Example: last_date = 2023-12-31
        forecast_start = 2024-01-01
        forecast_end   = 2024-06-30
    """
    forecast_start = last_date + pd.Timedelta(days=1)
    six_ahead      = forecast_start + pd.DateOffset(months=6)
    forecast_end   = six_ahead.replace(day=1) - pd.Timedelta(days=1)
    return forecast_start, forecast_end


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

def seasonal_naive_predict(train: pd.Series, steps: int, period: int = 7) -> np.ndarray:
    """
    7-day seasonal naive baseline.
    The prediction for day i equals the value from `period` days earlier
    (cycling through the last `period` values of the training series).
    """
    tail = list(train.values[-period:])
    return np.array([tail[i % period] for i in range(steps)], dtype=float)


def fit_holt_winters(train: pd.Series):
    """
    Fit Holt-Winters Exponential Smoothing with additive trend and additive
    weekly seasonality (seasonal_periods=7).  Warnings are suppressed.
    Returns the fitted model object.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ExponentialSmoothing(
            train,
            trend="add",
            seasonal="add",
            seasonal_periods=7,
        ).fit(optimized=True)


def holt_winters_predict(fitted_model, steps: int) -> np.ndarray:
    """Forecast `steps` days ahead, clipping any negative values to 0."""
    return np.clip(fitted_model.forecast(steps).values, 0.0, None)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def calc_mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Mean Absolute Error."""
    return float(np.mean(np.abs(actual - predicted)))


def calc_rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Root Mean Squared Error."""
    return float(np.sqrt(np.mean((actual - predicted) ** 2)))


def calc_mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    """
    Mean Absolute Percentage Error.
    Rows where actual == 0 are silently skipped to avoid division by zero.
    Returns NaN if no non-zero actuals exist.
    """
    mask = actual != 0
    if mask.sum() == 0:
        return float("nan")
    return float(
        np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100
    )


# ---------------------------------------------------------------------------
# Model comparison
# ---------------------------------------------------------------------------

def evaluate_models(train: pd.Series, test: pd.Series) -> list:
    """
    Train both models on `train` and evaluate on `test`.

    Returns a list of dicts sorted by MAE ascending.  The first entry is the
    selected (best) model and carries selected=True.  Each dict also contains
    a `residuals` key (np.ndarray) for downstream bound calculation – this
    key is not written to CSV.
    """
    actual = test.values
    results = []

    # Model A – seasonal naive
    naive_preds     = seasonal_naive_predict(train, len(test))
    naive_residuals = actual - naive_preds
    results.append({
        "model":     "Seasonal Naive",
        "mae":       round(calc_mae(actual, naive_preds),  4),
        "rmse":      round(calc_rmse(actual, naive_preds), 4),
        "mape":      round(calc_mape(actual, naive_preds), 4),
        "residuals": naive_residuals,
    })

    # Model B – Holt-Winters
    hw_fitted    = fit_holt_winters(train)
    hw_preds     = holt_winters_predict(hw_fitted, len(test))
    hw_residuals = actual - hw_preds
    results.append({
        "model":     "Holt-Winters",
        "mae":       round(calc_mae(actual, hw_preds),  4),
        "rmse":      round(calc_rmse(actual, hw_preds), 4),
        "mape":      round(calc_mape(actual, hw_preds), 4),
        "residuals": hw_residuals,
    })

    results.sort(key=lambda x: x["mae"])
    results[0]["selected"] = True
    for r in results[1:]:
        r["selected"] = False

    return results


def select_best_model(metrics: list) -> str:
    """Return the model name flagged as selected (lowest MAE)."""
    for m in metrics:
        if m.get("selected"):
            return m["model"]
    return min(metrics, key=lambda x: x["mae"])["model"]


# ---------------------------------------------------------------------------
# Future forecasting
# ---------------------------------------------------------------------------

def refit_and_forecast(daily: pd.Series, model_name: str, n_days: int) -> np.ndarray:
    """
    Refit the named model on the full `daily` series and return `n_days`
    of forward forecasts, clipped to >= 0.
    """
    if model_name == "Holt-Winters":
        fitted = fit_holt_winters(daily)
        return holt_winters_predict(fitted, n_days)
    # Seasonal naive fallback
    return np.clip(seasonal_naive_predict(daily, n_days), 0.0, None)


def calc_forecast_bounds(residuals: np.ndarray, forecast: np.ndarray):
    """
    Approximate 95% prediction bounds using holdout residual std.
    lower_bound is clipped to >= 0.
    These are NOT formal statistical confidence intervals.
    """
    std    = float(np.std(residuals))
    margin = 1.96 * std
    lower  = np.clip(forecast - margin, 0.0, None)
    upper  = forecast + margin
    return lower, upper


# ---------------------------------------------------------------------------
# Monthly aggregation
# ---------------------------------------------------------------------------

def aggregate_monthly(
    dates:    pd.DatetimeIndex,
    forecast: np.ndarray,
    lower:    np.ndarray,
    upper:    np.ndarray,
) -> list:
    """
    Aggregate daily forecast arrays into calendar months by summing.
    Returns a list of dicts sorted chronologically.

    Monthly bounds are the sums of the daily bounds for that month.
    """
    df = pd.DataFrame({
        "date":             dates,
        "forecast_revenue": forecast,
        "lower_bound":      lower,
        "upper_bound":      upper,
    })
    df["month"] = df["date"].dt.to_period("M").astype(str)

    monthly = (
        df.groupby("month")
        .agg(
            forecast_revenue=("forecast_revenue", "sum"),
            lower_bound=("lower_bound",      "sum"),
            upper_bound=("upper_bound",       "sum"),
        )
        .reset_index()
        .sort_values("month")
    )
    monthly["forecast_revenue"] = monthly["forecast_revenue"].apply(lambda v: round(float(v), 2))
    monthly["lower_bound"]      = monthly["lower_bound"].apply(lambda v: round(float(v), 2))
    monthly["upper_bound"]      = monthly["upper_bound"].apply(lambda v: round(float(v), 2))
    return monthly.to_dict("records")


# ---------------------------------------------------------------------------
# CSV readers for Django views
# ---------------------------------------------------------------------------

def read_forecast_csv(output_dir: str) -> dict:
    """
    Read forecast_summary.csv and monthly_sales_forecast.csv from output_dir.
    Raises FileNotFoundError if either file is missing.
    Returns a dict with all summary fields plus monthly_forecast list.
    """
    base     = Path(output_dir)
    summary  = pd.read_csv(base / "forecast_summary.csv").iloc[0].to_dict()
    monthly  = pd.read_csv(base / "monthly_sales_forecast.csv").to_dict("records")

    return {
        "selected_model":           str(summary["selected_model"]),
        "forecast_start_date":      str(summary["forecast_start_date"]),
        "forecast_end_date":        str(summary["forecast_end_date"]),
        "historical_total_revenue": round(float(summary["historical_total_revenue"]), 2),
        "forecast_total_revenue":   round(float(summary["forecast_total_revenue"]),   2),
        "expected_growth_percent":  round(float(summary["expected_growth_percent"]),  2),
        "best_model_mae":           round(float(summary["best_model_mae"]),           4),
        "best_model_rmse":          round(float(summary["best_model_rmse"]),          4),
        "best_model_mape":          round(float(summary["best_model_mape"]),          4),
        "monthly_forecast": [
            {
                "month":            str(r["month"]),
                "forecast_revenue": round(float(r["forecast_revenue"]), 2),
                "lower_bound":      round(float(r["lower_bound"]),      2),
                "upper_bound":      round(float(r["upper_bound"]),      2),
            }
            for r in monthly
        ],
    }


def read_metrics_csv(output_dir: str) -> dict:
    """
    Read model_metrics.csv from output_dir.
    Raises FileNotFoundError if the file is missing.
    Returns {"models": [...]} ready for JsonResponse.
    """
    df = pd.read_csv(Path(output_dir) / "model_metrics.csv")
    return {
        "models": [
            {
                "model":    str(row["model"]),
                "mae":      round(float(row["mae"]),  4),
                "rmse":     round(float(row["rmse"]), 4),
                "mape":     round(float(row["mape"]), 4),
                "selected": bool(row["selected"]),
            }
            for _, row in df.iterrows()
        ]
    }


# ---------------------------------------------------------------------------
# Deterministic recommendations
# ---------------------------------------------------------------------------

def generate_recommendations(
    forecast_data: dict,
    summary_data: dict | None = None,
    items_data: list | None = None,
) -> dict:
    """
    Generate rule-based, actionable recommendations for café owners.
    All claims are derived from the supplied data — nothing is hardcoded.

    Expected keys in forecast_data:
        expected_growth_percent, monthly_forecast, forecast_total_revenue,
        best_model_mae, best_model_mape
    Optional summary_data keys (from get_sales_summary):
        average_transaction_value, top_province, unknown_location_count,
        unknown_payment_method_count, total_rows
    Optional items_data: list of {item, total_revenue} dicts from get_item_breakdown
    """
    recs    = []
    growth  = float(forecast_data.get("expected_growth_percent", 0.0))
    monthly = forecast_data.get("monthly_forecast", [])
    total   = float(forecast_data.get("forecast_total_revenue", 0.0))
    mape    = forecast_data.get("best_model_mape")

    # --- High priority -------------------------------------------------------

    # Rule 1: revenue trend response
    if growth >= 0:
        recs.append({
            "priority": "high",
            "title":    "Capitalise on Positive Revenue Growth",
            "message":  (
                f"Revenue is forecast to grow by {growth:.1f}% over the next six months. "
                "This is the time to scale up: hire seasonal staff, increase stock orders, "
                "and launch a loyalty or referral programme to lock in returning customers."
            ),
            "evidence": f"Six-month forecast total: ${total:,.2f} · Growth: +{growth:.1f}%",
        })
    else:
        recs.append({
            "priority": "high",
            "title":    "Counter the Forecasted Revenue Decline",
            "message":  (
                f"Revenue is forecast to fall by {abs(growth):.1f}% over the next six months. "
                "Introduce limited-time offers and combo deals on high-margin items, "
                "revisit pricing on slower-selling products, and target lapsed customers "
                "with a win-back email or loyalty reward campaign."
            ),
            "evidence": f"Six-month forecast total: ${total:,.2f} · Growth: {growth:.1f}%",
        })

    # Rule 2: average transaction uplift (if summary available)
    if summary_data:
        atv = float(summary_data.get("average_transaction_value", 0.0))
        if atv > 0:
            target = round(atv * 1.15, 2)
            recs.append({
                "priority": "high",
                "title":    "Increase Average Transaction Value",
                "message":  (
                    f"The current average transaction is ${atv:,.2f}. "
                    f"Offering upsells at the till — a pastry with every hot drink, "
                    f"a size upgrade, or a meal deal — could push this to ${target:,.2f}, "
                    f"adding meaningful revenue without requiring more customers."
                ),
                "evidence": f"Current avg transaction: ${atv:,.2f} · Target: ${target:,.2f} (+15%)",
            })

    # --- Medium priority -----------------------------------------------------

    if monthly:
        # Rule 3: peak month preparation
        peak = max(monthly, key=lambda x: x["forecast_revenue"])
        recs.append({
            "priority": "medium",
            "title":    f"Prepare for Peak Demand in {peak['month']}",
            "message":  (
                f"{peak['month']} is the busiest forecast month at ${peak['forecast_revenue']:,.2f}. "
                "Confirm supplier contracts and delivery schedules at least four weeks in advance, "
                "schedule additional staff shifts, and pre-prepare best-selling items to reduce "
                "wait times during rush hours."
            ),
            "evidence": f"Forecast: ${peak['forecast_revenue']:,.2f}",
        })

        # Rule 4: slow month activation
        low = min(monthly, key=lambda x: x["forecast_revenue"])
        revenue_gap = peak["forecast_revenue"] - low["forecast_revenue"]
        recs.append({
            "priority": "medium",
            "title":    f"Run a Promotion Campaign in {low['month']}",
            "message":  (
                f"{low['month']} is the quietest forecast month at ${low['forecast_revenue']:,.2f} "
                f"— ${revenue_gap:,.2f} below the peak month. "
                "Run a targeted campaign: a weekday discount, a bundle deal, or a community event "
                "to bring in foot traffic during this slower window."
            ),
            "evidence": f"Forecast: ${low['forecast_revenue']:,.2f} · Gap vs peak: ${revenue_gap:,.2f}",
        })

    # Rule 5: top product bundle strategy (if item data available)
    if items_data and len(items_data) >= 2:
        top   = items_data[0]
        second = items_data[1]
        combined = top["total_revenue"] + second["total_revenue"]
        recs.append({
            "priority": "medium",
            "title":    f"Bundle {top['item']} and {second['item']} to Boost Sales",
            "message":  (
                f"{top['item']} and {second['item']} are your top two revenue-generating products, "
                f"together accounting for ${combined:,.2f} in 2023. "
                f"Pair them in a discounted combo deal to increase basket size, "
                "encourage customers who buy one to try the other, and improve perceived value."
            ),
            "evidence": (
                f"{top['item']}: ${top['total_revenue']:,.2f} · "
                f"{second['item']}: ${second['total_revenue']:,.2f}"
            ),
        })

    # Rule 6: focus on top province (if summary available)
    if summary_data:
        top_prov = summary_data.get("top_province")
        if top_prov:
            recs.append({
                "priority": "medium",
                "title":    f"Double Down on {top_prov}",
                "message":  (
                    f"{top_prov} is your highest-revenue province. "
                    "Prioritise regional marketing spend here — social media ads, local partnerships, "
                    "and in-store events. A strong performance in your top market will have the "
                    "biggest impact on overall revenue."
                ),
                "evidence": f"Top province by 2023 revenue: {top_prov}",
            })

    # --- Low priority --------------------------------------------------------

    # Rule 7: fix location data gaps (if summary available and significant)
    if summary_data:
        unknown_loc  = int(summary_data.get("unknown_location_count", 0))
        total_rows   = int(summary_data.get("total_rows", 10000))
        loc_pct      = round(unknown_loc / total_rows * 100, 1) if total_rows > 0 else 0
        if unknown_loc > 0:
            recs.append({
                "priority": "low",
                "title":    "Fix Location Tracking to Unlock Regional Insights",
                "message":  (
                    f"{unknown_loc:,} transactions ({loc_pct}% of all sales) are missing a location. "
                    "This makes it impossible to compare performance across branches or delivery channels. "
                    "Work with your POS provider to enforce location capture on every transaction — "
                    "this is a one-time fix that pays off with every future analysis."
                ),
                "evidence": f"{unknown_loc:,} of {total_rows:,} records have no location",
            })

    # Rule 8: model accuracy note (brief, practical framing)
    if mape is not None:
        accuracy = max(0.0, 100.0 - float(mape))
        recs.append({
            "priority": "low",
            "title":    "Treat the Forecast as a Planning Guide, Not a Guarantee",
            "message":  (
                f"The forecasting model explains roughly {accuracy:.0f}% of revenue variation. "
                "Use the monthly figures to set staff rosters, stock orders, and budget targets — "
                "but review actuals every month and adjust plans as real data comes in."
            ),
            "evidence": f"Model MAPE: {float(mape):.1f}% · Indicative accuracy: ~{accuracy:.0f}%",
        })

    return {"recommendations": recs}
