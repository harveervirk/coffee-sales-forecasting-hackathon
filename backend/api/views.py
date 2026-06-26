from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from .forecasting import (
    generate_recommendations,
    read_forecast_csv,
    read_metrics_csv,
)
from .services import (
    get_data_quality_report,
    get_item_breakdown,
    get_location_breakdown,
    get_monthly_trends,
    get_payment_breakdown,
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


@require_GET
def sales_payments(request):
    return JsonResponse(get_payment_breakdown(str(SALES_FILE)), safe=False)


@require_GET
def data_quality_report(request):
    return JsonResponse(get_data_quality_report(str(SALES_FILE)))


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

    return JsonResponse(generate_recommendations(data))


# ---------------------------------------------------------------------------
# Portal pages (server-rendered; all data loaded client-side via the APIs)
# ---------------------------------------------------------------------------

def overview(request):
    return render(request, 'api/overview.html', {'active_page': 'overview'})


def analytics(request):
    return render(request, 'api/analytics.html', {'active_page': 'analytics'})


def forecast_centre(request):
    return render(request, 'api/forecast_centre.html', {'active_page': 'forecast-centre'})


def recommendations_page(request):
    return render(request, 'api/recommendations.html', {'active_page': 'recommendations-page'})


def data_quality(request):
    return render(request, 'api/data_quality.html', {'active_page': 'data-quality'})


def scenario_lab(request):
    return render(request, 'api/scenario_lab.html', {'active_page': 'scenario-lab'})
