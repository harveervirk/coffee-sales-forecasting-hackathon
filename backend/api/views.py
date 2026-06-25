from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .forecasting import (
    generate_recommendations,
    read_forecast_csv,
    read_metrics_csv,
)
from .services import (
    get_item_breakdown,
    get_location_breakdown,
    get_monthly_trends,
    get_province_breakdown,
    get_sales_summary,
)

SALES_FILE = (
    Path(settings.BASE_DIR).parent
    / "data"
    / "CanAI Cafe 2023 Sales Information UPDATED.xlsx"
)

OUTPUT_DIR = Path(settings.BASE_DIR).parent / "analysis" / "outputs"

_FORECAST_NOT_READY = (
    "Forecast data is not available. "
    "Run python backend/manage.py generate_sales_forecast."
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def health(request):
    return JsonResponse({'status': 'ok'})


# ---------------------------------------------------------------------------
# Sales analytics (existing)
# ---------------------------------------------------------------------------

@require_GET
def sales_summary(request):
    return JsonResponse(get_sales_summary(str(SALES_FILE)))


@require_GET
def sales_trends(request):
    return JsonResponse(get_monthly_trends(str(SALES_FILE)), safe=False)


@require_GET
def sales_items(request):
    return JsonResponse(get_item_breakdown(str(SALES_FILE)), safe=False)


@require_GET
def sales_provinces(request):
    return JsonResponse(get_province_breakdown(str(SALES_FILE)), safe=False)


@require_GET
def sales_locations(request):
    return JsonResponse(get_location_breakdown(str(SALES_FILE)), safe=False)


# ---------------------------------------------------------------------------
# Forecasting endpoints
# ---------------------------------------------------------------------------

@require_GET
def forecast(request):
    """
    GET /api/forecast/
    Returns the six-month monthly forecast and summary metrics.
    Responds 503 if the forecast CSVs have not been generated yet.
    """
    try:
        data = read_forecast_csv(str(OUTPUT_DIR))
    except FileNotFoundError:
        return JsonResponse({"error": _FORECAST_NOT_READY}, status=503)

    return JsonResponse({
        "selected_model":          data["selected_model"],
        "forecast_start_date":     data["forecast_start_date"],
        "forecast_end_date":       data["forecast_end_date"],
        "forecast_total_revenue":  data["forecast_total_revenue"],
        "expected_growth_percent": data["expected_growth_percent"],
        "monthly_forecast":        data["monthly_forecast"],
    })


@require_GET
def forecast_metrics(request):
    """
    GET /api/forecast/metrics/
    Returns evaluation metrics for all trained models.
    Responds 503 if the forecast CSVs have not been generated yet.
    """
    try:
        data = read_metrics_csv(str(OUTPUT_DIR))
    except FileNotFoundError:
        return JsonResponse({"error": _FORECAST_NOT_READY}, status=503)

    return JsonResponse(data)


@require_GET
def recommendations(request):
    """
    GET /api/recommendations/
    Returns deterministic recommendations derived from actual forecast values.
    Responds 503 if the forecast CSVs have not been generated yet.
    """
    try:
        data = read_forecast_csv(str(OUTPUT_DIR))
    except FileNotFoundError:
        return JsonResponse({"error": _FORECAST_NOT_READY}, status=503)
   
    # NEW: Get item data for product recommendations
    items_data = get_item_breakdown(str(SALES_FILE))

    return JsonResponse(generate_recommendations(data, items_data))
