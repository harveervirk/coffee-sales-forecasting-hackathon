from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .services import get_sales_summary

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
