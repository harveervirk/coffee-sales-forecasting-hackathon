from pathlib import Path

import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand

from api.services import (
    get_item_breakdown,
    get_location_breakdown,
    get_monthly_trends,
    get_province_breakdown,
)

SALES_FILE = (
    Path(settings.BASE_DIR).parent
    / "data"
    / "CanAI Cafe 2023 Sales Information - CLeaned.xlsx"
)

OUTPUT_DIR = Path(settings.BASE_DIR).parent / "analysis" / "outputs"


class Command(BaseCommand):
    help = "Export aggregated sales data to analysis/outputs/ as CSV files."

    def handle(self, *args, **options):
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filepath = str(SALES_FILE)

        exports = [
            ("monthly_sales.csv",  get_monthly_trends(filepath)),
            ("item_sales.csv",     get_item_breakdown(filepath)),
            ("province_sales.csv", get_province_breakdown(filepath)),
            ("location_sales.csv", get_location_breakdown(filepath)),
        ]

        for filename, records in exports:
            out_path = OUTPUT_DIR / filename
            df = pd.DataFrame(records)
            df.to_csv(out_path, index=False)
            self.stdout.write(f"  {filename}: {len(df)} rows → {out_path}")

        self.stdout.write(self.style.SUCCESS("Export complete."))
