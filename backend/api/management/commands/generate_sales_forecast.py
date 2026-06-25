"""
Management command: generate_sales_forecast

Runs the full forecasting pipeline and writes five CSV output files:
  - daily_sales_history.csv
  - model_metrics.csv
  - daily_sales_forecast.csv
  - monthly_sales_forecast.csv
  - forecast_summary.csv

Usage:
    python backend/manage.py generate_sales_forecast
"""
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from api.forecasting import (
    aggregate_monthly,
    calc_forecast_bounds,
    evaluate_models,
    get_forecast_period,
    load_daily_sales,
    refit_and_forecast,
    select_best_model,
    split_train_test,
)

SALES_FILE = (
    Path(settings.BASE_DIR).parent
    / "data"
    / "CanAI Cafe 2023 Sales Information UPDATED.xlsx"
)

OUTPUT_DIR = Path(settings.BASE_DIR).parent / "analysis" / "outputs"


class Command(BaseCommand):
    help = "Train forecasting models and write six-month sales forecasts to CSV."

    def handle(self, *args, **options):

        # ------------------------------------------------------------------ #
        # 1. Source file guard
        # ------------------------------------------------------------------ #
        if not SALES_FILE.exists():
            raise CommandError(f"Source workbook not found: {SALES_FILE}")

        # ------------------------------------------------------------------ #
        # 2. Load and prepare daily data
        # ------------------------------------------------------------------ #
        self.stdout.write("Loading daily sales data …")
        daily = load_daily_sales(str(SALES_FILE))
        self.stdout.write(
            f"  {len(daily)} daily records  "
            f"({daily.index.min().date()} → {daily.index.max().date()})"
        )

        # ------------------------------------------------------------------ #
        # 3. Train / test split
        # ------------------------------------------------------------------ #
        train, test = split_train_test(daily)
        self.stdout.write(f"  Training rows : {len(train)}")
        self.stdout.write(f"  Test rows     : {len(test)}")

        # ------------------------------------------------------------------ #
        # 4. Evaluate both models
        # ------------------------------------------------------------------ #
        self.stdout.write("\nTraining and evaluating models …")
        metrics = evaluate_models(train, test)

        for m in metrics:
            tag = " ← selected" if m["selected"] else ""
            self.stdout.write(
                f"  {m['model']:20s}  MAE={m['mae']:.2f}  "
                f"RMSE={m['rmse']:.2f}  MAPE={m['mape']:.2f}%{tag}"
            )

        # ------------------------------------------------------------------ #
        # 5. Select best model + extract its test residuals
        # ------------------------------------------------------------------ #
        best_name     = select_best_model(metrics)
        best_meta     = next(m for m in metrics if m["model"] == best_name)
        best_residuals = best_meta["residuals"]
        self.stdout.write(f"\nSelected model: {best_name}")

        # ------------------------------------------------------------------ #
        # 6. Determine forecast period
        # ------------------------------------------------------------------ #
        forecast_start, forecast_end = get_forecast_period(daily.index.max())
        n_days = (forecast_end - daily.index.max()).days
        self.stdout.write(
            f"Forecast period: {forecast_start.date()} → "
            f"{forecast_end.date()} ({n_days} days)"
        )

        # ------------------------------------------------------------------ #
        # 7. Refit on full data and generate forecast
        # ------------------------------------------------------------------ #
        self.stdout.write(f"\nRefitting {best_name} on full dataset …")
        forecast_values = refit_and_forecast(daily, best_name, n_days)
        forecast_dates  = pd.date_range(forecast_start, periods=n_days, freq="D")

        # ------------------------------------------------------------------ #
        # 8. Approximate prediction bounds
        # ------------------------------------------------------------------ #
        lower, upper = calc_forecast_bounds(best_residuals, forecast_values)

        # ------------------------------------------------------------------ #
        # 9. Monthly aggregation
        # ------------------------------------------------------------------ #
        monthly_records = aggregate_monthly(forecast_dates, forecast_values, lower, upper)

        # ------------------------------------------------------------------ #
        # 10. Historical comparison for expected growth
        #     Compare forecast (Jan-Jun 2024) to same calendar window in 2023.
        # ------------------------------------------------------------------ #
        compare_start = max(
            forecast_start - pd.DateOffset(years=1),
            daily.index.min(),
        )
        compare_end = min(
            forecast_end - pd.DateOffset(years=1),
            daily.index.max(),
        )
        historical_comparable = float(daily[compare_start:compare_end].sum())
        forecast_total        = round(float(forecast_values.sum()), 2)

        if historical_comparable > 0:
            expected_growth = round(
                (forecast_total - historical_comparable) / historical_comparable * 100, 2
            )
        else:
            expected_growth = 0.0

        # ------------------------------------------------------------------ #
        # 11. Write output CSV files
        # ------------------------------------------------------------------ #
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        # --- daily_sales_history.csv ---
        hist_df   = pd.DataFrame({
            "date":           daily.index.strftime("%Y-%m-%d"),
            "actual_revenue": daily.values.astype(float),
        })
        hist_path = OUTPUT_DIR / "daily_sales_history.csv"
        hist_df.to_csv(hist_path, index=False)

        # --- model_metrics.csv ---
        metrics_rows = [
            {
                "model":    m["model"],
                "mae":      m["mae"],
                "rmse":     m["rmse"],
                "mape":     m["mape"],
                "selected": m["selected"],
            }
            for m in metrics
        ]
        metrics_df   = pd.DataFrame(metrics_rows)
        metrics_path = OUTPUT_DIR / "model_metrics.csv"
        metrics_df.to_csv(metrics_path, index=False)

        # --- daily_sales_forecast.csv ---
        daily_fc_df   = pd.DataFrame({
            "date":             forecast_dates.strftime("%Y-%m-%d"),
            "forecast_revenue": [round(float(v), 2) for v in forecast_values],
            "lower_bound":      [round(float(v), 2) for v in lower],
            "upper_bound":      [round(float(v), 2) for v in upper],
        })
        daily_fc_path = OUTPUT_DIR / "daily_sales_forecast.csv"
        daily_fc_df.to_csv(daily_fc_path, index=False)

        # --- monthly_sales_forecast.csv ---
        monthly_df    = pd.DataFrame(monthly_records)
        monthly_path  = OUTPUT_DIR / "monthly_sales_forecast.csv"
        monthly_df.to_csv(monthly_path, index=False)

        # --- forecast_summary.csv ---
        summary_df   = pd.DataFrame([{
            "selected_model":           best_name,
            "forecast_start_date":      forecast_start.strftime("%Y-%m-%d"),
            "forecast_end_date":        forecast_end.strftime("%Y-%m-%d"),
            "historical_total_revenue": round(float(daily.sum()), 2),
            "forecast_total_revenue":   forecast_total,
            "expected_growth_percent":  expected_growth,
            "best_model_mae":           best_meta["mae"],
            "best_model_rmse":          best_meta["rmse"],
            "best_model_mape":          best_meta["mape"],
        }])
        summary_path = OUTPUT_DIR / "forecast_summary.csv"
        summary_df.to_csv(summary_path, index=False)

        # ------------------------------------------------------------------ #
        # 12. Print output file report
        # ------------------------------------------------------------------ #
        self.stdout.write("\nGenerated files:")
        for label, df, path in [
            ("daily_sales_history.csv",    hist_df,      hist_path),
            ("model_metrics.csv",          metrics_df,   metrics_path),
            ("daily_sales_forecast.csv",   daily_fc_df,  daily_fc_path),
            ("monthly_sales_forecast.csv", monthly_df,   monthly_path),
            ("forecast_summary.csv",       summary_df,   summary_path),
        ]:
            self.stdout.write(f"  {label}: {len(df)} rows → {path}")

        self.stdout.write(self.style.SUCCESS("\nForecast generation complete."))
