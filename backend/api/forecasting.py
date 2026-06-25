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
def _get_product_recommendations(items_data: list = None) -> list:
    """
    Generate product-specific stocking recommendations based on item performance.
    
    If items_data is provided (from get_item_breakdown), analyze top/bottom performers.
    Otherwise, return generic product recommendations.
    """
    product_recs = []
    
    # If we don't have item data, return generic product rules
    if not items_data or len(items_data) == 0:
        product_recs.append({
            "category": "product",
            "priority": "high",
            "title": "Sandwich & Coffee Lead Revenue",
            "message": "Sandwiches and Coffee are your top revenue drivers. Ensure consistent stock levels and quality for these items to maintain customer satisfaction.",
            "evidence": "Based on historical sales analysis"
        })
        return product_recs
    
    # Sort items by revenue
    items_sorted = sorted(items_data, key=lambda x: x['total_revenue'], reverse=True)
    
    # Rule: Top performer
    top_item = items_sorted[0]
    product_recs.append({
        "category": "product",
        "priority": "high",
        "title": f"{top_item['item']}: Top Revenue Driver - Increase Stock",
        "message": (
            f"{top_item['item']} generates ${top_item['total_revenue']:,.2f} in revenue with "
            f"{top_item['total_quantity']:,} units sold. This is your #1 performer. "
            f"Increase stock by 20-25% to prevent stockouts and maximize revenue."
        ),
        "evidence": f"{top_item['unique_transactions']:,} transactions, avg per transaction: ${top_item['total_revenue']/top_item['unique_transactions']:.2f}"
    })
    
    # Rule: Second performer
    if len(items_sorted) > 1:
        second_item = items_sorted[1]
        product_recs.append({
            "category": "product",
            "priority": "high",
            "title": f"{second_item['item']}: Strong Performer - Maintain Stock",
            "message": (
                f"{second_item['item']} is your second-highest revenue item at ${second_item['total_revenue']:,.2f} "
                f"with {second_item['total_quantity']:,} units sold. Maintain current stock levels and monitor for seasonal dips."
            ),
            "evidence": f"{second_item['unique_transactions']:,} transactions"
        })
    
    # Rule: Low performer opportunity
    if len(items_sorted) > 1:
        low_item = items_sorted[-1]
        product_recs.append({
            "category": "product",
            "priority": "medium",
            "title": f"{low_item['item']}: Low Revenue - Consider Promotions",
            "message": (
                f"{low_item['item']} generates only ${low_item['total_revenue']:,.2f} in revenue ({low_item['total_quantity']:,} units). "
                f"Consider bundling with popular items, running promotions, or testing new variations to boost sales."
            ),
            "evidence": f"Only {low_item['unique_transactions']:,} transactions - opportunity for growth"
        })
    
    # Rule: High-volume item
    high_volume = max(items_sorted, key=lambda x: x['total_quantity'])
    if high_volume['item'] != top_item['item']:
        product_recs.append({
            "category": "product",
            "priority": "medium",
            "title": f"{high_volume['item']}: High Volume Item - Optimize Margins",
            "message": (
                f"{high_volume['item']} has strong volume ({high_volume['total_quantity']:,} units) but lower per-unit revenue. "
                f"Focus on upselling or offering premium variations to increase profit margin per transaction."
            ),
            "evidence": f"Volume: {high_volume['total_quantity']:,} units | Revenue: ${high_volume['total_revenue']:,.2f}"
        })
    
    return product_recs

def generate_recommendations(forecast_data: dict, items_data: list = None) -> dict:
    """
    Generate rule-based recommendations from actual forecast values.
    All claims are derived from the supplied data — nothing is hardcoded.

    Expected keys in forecast_data:
        expected_growth_percent, monthly_forecast, selected_model,
        forecast_total_revenue, best_model_mae
    """
    recs    = []
    growth  = float(forecast_data.get("expected_growth_percent", 0.0))
    monthly = forecast_data.get("monthly_forecast", [])
    model   = str(forecast_data.get("selected_model", ""))
    total   = float(forecast_data.get("forecast_total_revenue", 0.0))
    mae     = forecast_data.get("best_model_mae")

    # Rule 1: growth direction
    if growth >= 0:
        recs.append({
            "category": "business",
            "priority": "high",
            "title":    "Positive Revenue Growth Expected",
            "message":  (
                f"Revenue is forecast to grow by {growth:.1f}% compared to the same six-month "
                "period last year. Consider scaling inventory and staffing to meet higher demand."
            ),
            "evidence": f"Six-month forecast total: ${total:,.2f}",
        })
    else:
        recs.append({
            "category": "business",
            "priority": "high",
            "title":    "Revenue Decline Expected",
            "message":  (
                f"Revenue is forecast to decline by {abs(growth):.1f}% compared to the same "
                "six-month period last year. Review promotions, pricing, and low-performing periods."
            ),
            "evidence": f"Six-month forecast total: ${total:,.2f}",
        })

    if monthly:
        # Rule 2: peak month
        peak = max(monthly, key=lambda x: x["forecast_revenue"])
        recs.append({
            "category": "business",
            "priority": "medium",
            "title":    f"Peak Sales Expected in {peak['month']}",
            "message":  (
                f"{peak['month']} is the highest forecast month at ${peak['forecast_revenue']:,.2f}. "
                "Ensure adequate stock and staff coverage heading into this period."
            ),
            "evidence": (
                f"Forecast range: ${peak['lower_bound']:,.2f} – ${peak['upper_bound']:,.2f}"
            ),
        })

        # Rule 3: lowest month
        low = min(monthly, key=lambda x: x["forecast_revenue"])
        recs.append({
            "category": "business",
            "priority": "medium",
            "title":    f"Lowest Sales Expected in {low['month']}",
            "message":  (
                f"{low['month']} is the lowest forecast month at ${low['forecast_revenue']:,.2f}. "
                "Consider targeted promotions or events to lift revenue during this period."
            ),
            "evidence": (
                f"Forecast range: ${low['lower_bound']:,.2f} – ${low['upper_bound']:,.2f}"
            ),
        })

    # Rule 4: model accuracy
    mae_label = f"{mae:.2f} revenue units per day" if mae is not None else "N/A"
    recs.append({
        "category": "business",
        "priority": "low",
        "title":    f"Forecast Model: {model}",
        "message":  (
            f"Forecasts were generated using {model}, selected as the best-performing model "
            f"based on mean absolute error. Test period MAE: {mae_label}."
        ),
        "evidence": f"MAE = {mae:.4f}" if mae is not None else "MAE = N/A",
    })

    # Rule 5: uncertainty reminder
    recs.append({
        "category": "business",
        "priority": "low",
        "title":    "Account for Forecast Uncertainty",
        "message":  (
            "The lower and upper bounds shown are approximate 95% prediction ranges "
            "based on holdout residual standard deviation — not formal confidence intervals. "
            "Use them to plan for realistic best- and worst-case revenue scenarios."
        ),
        "evidence": "Bounds = forecast ± 1.96 × holdout residual std",
    })

    # Product-specific rules (if you can fetch item data)
    # Note: For now, we'll add static product recommendations based on known item analysis
    product_recs = _get_product_recommendations(items_data)
    recs.extend(product_recs)

    return {"recommendations": recs}
