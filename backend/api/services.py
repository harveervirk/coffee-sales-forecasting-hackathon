import pandas as pd

KNOWN_PAYMENTS = {"Cash", "Credit Card", "Digital Wallet"}
KNOWN_LOCATIONS = {"In-store", "Takeaway"}
VALID_PROVINCES = {
    "British Columbia",
    "Manitoba",
    "Saskatchewan",
    "Newfoundland",
    "Ontario",
}
ALLOWED_LOCATIONS_WITH_UNKNOWN = {"In-store", "Takeaway", "UNKNOWN"}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _load_and_normalise(filepath: str) -> pd.DataFrame:
    """Load the Excel file, normalise text columns, and parse dates."""
    df = pd.read_excel(filepath)
    df["Item"] = df["Item"].str.strip().str.title()
    df["Province"] = df["Province"].str.strip().str.title()
    df["parsed_date"] = pd.to_datetime(df["Transaction Date"], errors="coerce")
    return df


def _agg_to_records(df: pd.DataFrame, group_col: str, out_col: str) -> list:
    """
    Group df by group_col, compute total_revenue / total_quantity /
    unique_transactions, sort by total_revenue descending, and return
    a list of plain Python dicts with JSON-safe types.
    """
    agg = (
        df.groupby(group_col)
        .agg(
            total_revenue=("Total Spent", "sum"),
            total_quantity=("Quantity", "sum"),
            unique_transactions=("Transaction ID", "nunique"),
        )
        .reset_index()
        .sort_values("total_revenue", ascending=False)
        .rename(columns={group_col: out_col})
    )
    agg["total_revenue"] = agg["total_revenue"].astype(float)
    agg["total_quantity"] = agg["total_quantity"].astype(int)
    agg["unique_transactions"] = agg["unique_transactions"].astype(int)
    return agg[[out_col, "total_revenue", "total_quantity", "unique_transactions"]].to_dict("records")


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

def get_sales_summary(filepath: str) -> dict:
    df = _load_and_normalise(filepath)

    invalid_date_count = int(df["parsed_date"].isna().sum())
    valid_dates = df["parsed_date"].dropna()
    earliest_date = valid_dates.min().strftime("%Y-%m-%d")
    latest_date = valid_dates.max().strftime("%Y-%m-%d")

    total_revenue = float(df["Total Spent"].sum())
    total_quantity = int(df["Quantity"].sum())
    unique_transactions = int(df["Transaction ID"].nunique())

    txn_totals = df.groupby("Transaction ID")["Total Spent"].sum()
    average_transaction_value = round(float(txn_totals.mean()), 2)

    top_item = df["Item"].value_counts().idxmax()

    valid_province_mask = df["Province"].isin(VALID_PROVINCES)
    top_province = df.loc[valid_province_mask, "Province"].value_counts().idxmax()

    unknown_payment_method_count = int((~df["Payment Method"].isin(KNOWN_PAYMENTS)).sum())
    unknown_location_count = int((~df["Location"].isin(KNOWN_LOCATIONS)).sum())

    return {
        "total_rows": len(df),
        "total_revenue": total_revenue,
        "total_quantity": total_quantity,
        "unique_transactions": unique_transactions,
        "average_transaction_value": average_transaction_value,
        "top_item": top_item,
        "top_province": top_province,
        "earliest_date": earliest_date,
        "latest_date": latest_date,
        "invalid_date_count": invalid_date_count,
        "unknown_payment_method_count": unknown_payment_method_count,
        "unknown_location_count": unknown_location_count,
    }


def get_monthly_trends(filepath: str) -> list:
    """Return monthly aggregates for 2023, sorted chronologically."""
    df = _load_and_normalise(filepath)
    valid = df[df["parsed_date"].notna()].copy()
    valid["month"] = valid["parsed_date"].dt.to_period("M").astype(str)
    agg = (
        valid.groupby("month")
        .agg(
            total_revenue=("Total Spent", "sum"),
            total_quantity=("Quantity", "sum"),
            unique_transactions=("Transaction ID", "nunique"),
        )
        .reset_index()
        .sort_values("month")
    )
    agg["total_revenue"] = agg["total_revenue"].astype(float)
    agg["total_quantity"] = agg["total_quantity"].astype(int)
    agg["unique_transactions"] = agg["unique_transactions"].astype(int)
    return agg.to_dict("records")


def get_item_breakdown(filepath: str) -> list:
    """Return per-item aggregates sorted by total_revenue descending."""
    df = _load_and_normalise(filepath)
    return _agg_to_records(df, "Item", "item")


def get_province_breakdown(filepath: str) -> list:
    """Return per-province aggregates (valid provinces only), sorted by total_revenue descending."""
    df = _load_and_normalise(filepath)
    valid = df[df["Province"].isin(VALID_PROVINCES)]
    return _agg_to_records(valid, "Province", "province")


def get_location_breakdown(filepath: str) -> list:
    """Return per-location aggregates (In-store, Takeaway, UNKNOWN), sorted by total_revenue descending."""
    df = _load_and_normalise(filepath)
    allowed = df[df["Location"].isin(ALLOWED_LOCATIONS_WITH_UNKNOWN)]
    return _agg_to_records(allowed, "Location", "location")


def get_payment_breakdown(filepath: str) -> list:
    """Return per-payment-method counts and percentages, sorted by count descending."""
    df = pd.read_excel(filepath)
    total = len(df)
    counts = df["Payment Method"].value_counts()
    return [
        {
            "method": str(method),
            "count": int(count),
            "pct": round(float(count) / total * 100, 1),
        }
        for method, count in counts.items()
    ]


def get_data_quality_report(filepath: str) -> dict:
    """Return a data quality report with computed cleaning action details."""
    df = pd.read_excel(filepath)
    total_rows = len(df)

    parsed_dates = pd.to_datetime(df["Transaction Date"], errors="coerce")
    invalid_date_count = int(parsed_dates.isna().sum())
    unknown_payment_count = int((~df["Payment Method"].isin(KNOWN_PAYMENTS)).sum())
    unknown_location_count = int((~df["Location"].isin(KNOWN_LOCATIONS)).sum())
    duplicate_count = total_rows - int(df["Transaction ID"].nunique())

    item_raw = df["Item"].astype(str)
    item_norm = item_raw.str.strip().str.title()
    item_inconsistencies = int((item_raw != item_norm).sum())

    prov_raw = df["Province"].astype(str)
    prov_norm = prov_raw.str.strip().str.title()
    province_inconsistencies = int((prov_raw != prov_norm).sum())

    cleaning_actions = [
        {
            "issue": "Duplicate Transaction IDs",
            "affected": duplicate_count,
            "resolution": "Excluded from unique-transaction count",
            "reason": "Duplicate TXN IDs may be re-submitted orders or data-entry errors.",
            "status": "Retained",
        },
        {
            "issue": "Invalid Transaction Dates",
            "affected": invalid_date_count,
            "resolution": "Excluded from forecasting; revenue counted in totals",
            "reason": "Unparseable dates cannot be placed on a time axis.",
            "status": "Corrected",
        },
        {
            "issue": "Unknown Payment Methods",
            "affected": unknown_payment_count,
            "resolution": "Retained with \"Unknown\" label",
            "reason": "Revenue is valid; only the payment channel is unidentifiable.",
            "status": "Retained",
        },
        {
            "issue": "Unknown Location Values",
            "affected": unknown_location_count,
            "resolution": "Categorised as \"UNKNOWN\" in location breakdowns",
            "reason": "Location data is incomplete but revenue is real.",
            "status": "Retained",
        },
        {
            "issue": "Province Name Inconsistencies",
            "affected": province_inconsistencies,
            "resolution": "Whitespace trimmed; Title Case applied",
            "reason": "Inconsistent casing caused provinces to appear as multiple entries.",
            "status": "Corrected",
        },
        {
            "issue": "Item Name Inconsistencies",
            "affected": item_inconsistencies,
            "resolution": "Whitespace trimmed; Title Case applied",
            "reason": "Normalised names enable accurate product-level aggregation.",
            "status": "Corrected",
        },
    ]

    return {
        "total_rows": total_rows,
        "cleaning_actions": cleaning_actions,
    }
