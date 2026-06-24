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


def get_sales_summary(filepath: str) -> dict:
    df = pd.read_excel(filepath)

    # --- Normalize text columns to collapse whitespace/case duplicates ---
    df["Item"] = df["Item"].str.strip().str.title()
    df["Province"] = df["Province"].str.strip().str.title()

    # --- Date handling ---
    # errors="coerce" turns any value that cannot be parsed into NaT
    parsed_dates = pd.to_datetime(df["Transaction Date"], errors="coerce")
    invalid_date_count = int(parsed_dates.isna().sum())
    valid_dates = parsed_dates.dropna()
    earliest_date = valid_dates.min().strftime("%Y-%m-%d")
    latest_date = valid_dates.max().strftime("%Y-%m-%d")

    # --- Revenue and quantity ---
    total_revenue = float(df["Total Spent"].sum())
    total_quantity = int(df["Quantity"].sum())

    # --- Transactions ---
    unique_transactions = int(df["Transaction ID"].nunique())

    # average per unique transaction: group rows by Transaction ID,
    # sum Total Spent within each transaction, then average those totals
    txn_totals = df.groupby("Transaction ID")["Total Spent"].sum()
    average_transaction_value = round(float(txn_totals.mean()), 2)

    # --- Top item (after normalisation) ---
    top_item = df["Item"].value_counts().idxmax()

    # --- Top province: only consider known valid provinces ---
    valid_province_mask = df["Province"].isin(VALID_PROVINCES)
    top_province = df.loc[valid_province_mask, "Province"].value_counts().idxmax()

    # --- Data quality counts ---
    unknown_payment_method_count = int((~df["Payment Method"].isin(KNOWN_PAYMENTS)).sum())
    unknown_location_count = int((~df["Location"].isin(KNOWN_LOCATIONS)).sum())

    return {
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
