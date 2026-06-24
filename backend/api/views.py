from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET

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
    / "CanAI Cafe 2023 Sales Information - CLeaned.xlsx"
)


def health(request):
    return JsonResponse({'status': 'ok'})


@require_GET
def sales_summary(request):
    summary = get_sales_summary(str(SALES_FILE))
    return JsonResponse(summary)


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
