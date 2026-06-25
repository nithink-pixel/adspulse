import pandas as pd
import duckdb
import os
from datetime import datetime

DB_PATH        = "data/adspulse.duckdb"
QUARANTINE_DIR = "data/quarantine"

os.makedirs(QUARANTINE_DIR, exist_ok=True)

# ── Validation rules ──────────────────────────────────────────────────────────
def validate_campaign(df):
    results = []
    quarantine_mask = pd.Series([False] * len(df))

    rules = [
        ("R01", "No negative spend",            df["spend"] < 0),
        ("R02", "Clicks <= Impressions",         df["clicks"] > df["impressions"]),
        ("R03", "Conversions <= Clicks",         df["conversions"] > df["clicks"]),
        ("R04", "No null advertiser_id",         df["advertiser_id"].isnull()),
        ("R05", "No null campaign_id",           df["campaign_id"].isnull()),
        ("R06", "No null date",                  df["date"].isnull()),
        ("R07", "Spend not excessively high",    df["spend"] > 50000),
        ("R08", "Impressions > 0",               df["impressions"] <= 0),
        ("R09", "Revenue >= 0",                  df["revenue"] < 0),
        ("R10", "No null channel",               df["channel"].isnull()),
        ("R11", "No null region",                df["region"].isnull()),
        ("R12", "No zero-click with conversions", (df["clicks"] == 0) & (df["conversions"] > 0)),
    ]

    for rule_id, rule_name, mask in rules:
        failed = int(mask.sum())
        passed = len(df) - failed
        results.append({
            "rule_id":    rule_id,
            "rule":       rule_name,
            "passed":     passed,
            "failed":     failed,
            "pass_rate":  round(passed / len(df) * 100, 2),
            "status":     "✓ PASS" if failed == 0 else "✗ FAIL"
        })
        quarantine_mask |= mask

    return results, quarantine_mask

def compute_kpis(df):
    df = df.copy()
    eps = 1e-9
    df["ctr"]             = (df["clicks"]      / (df["impressions"] + eps)).round(4)
    df["cpc"]             = (df["spend"]        / (df["clicks"]      + eps)).round(2)
    df["cpm"]             = (df["spend"]        / ((df["impressions"] / 1000) + eps)).round(2)
    df["conversion_rate"] = (df["conversions"]  / (df["clicks"]      + eps)).round(4)
    df["roas"]            = (df["revenue"]      / (df["spend"]       + eps)).round(2)
    df["cpa"]             = (df["spend"]        / (df["conversions"] + eps)).round(2)
    df["month"]           = pd.to_datetime(df["date"]).dt.month
    df["quarter"]         = pd.to_datetime(df["date"]).dt.quarter
    df["year"]            = pd.to_datetime(df["date"]).dt.year
    return df

def run_etl():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting ETL...\n")

    # Load raw
    perf     = pd.read_csv("data/raw/fact_campaign_performance.csv")
    pipeline = pd.read_csv("data/raw/fact_sales_pipeline.csv")
    budget   = pd.read_csv("data/raw/fact_budget_targets.csv")
    adv      = pd.read_csv("data/raw/dim_advertisers.csv")

    print(f"Raw records loaded: {len(perf):,}")

    # Validate
    validation_results, bad_mask = validate_campaign(perf)
    clean     = perf[~bad_mask].copy()
    quarantine = perf[bad_mask].copy()

    quality_score = round(len(clean) / len(perf) * 100, 2)
    print(f"Clean: {len(clean):,} | Quarantined: {len(quarantine):,} | Quality: {quality_score}%\n")

    # Quarantine
    if len(quarantine) > 0:
        quarantine.to_csv(f"{QUARANTINE_DIR}/campaign_quarantine.csv", index=False)

    # Save validation results
    val_df = pd.DataFrame(validation_results)
    val_df.to_csv(f"{QUARANTINE_DIR}/validation_report.csv", index=False)

    # Compute KPIs
    clean = compute_kpis(clean)

    # Load to DuckDB
    con = duckdb.connect(DB_PATH)

    con.execute("DROP TABLE IF EXISTS fact_campaign_performance")
    con.execute("CREATE TABLE fact_campaign_performance AS SELECT * FROM clean")

    con.execute("DROP TABLE IF EXISTS fact_sales_pipeline")
    con.execute("CREATE TABLE fact_sales_pipeline AS SELECT * FROM pipeline")

    con.execute("DROP TABLE IF EXISTS fact_budget_targets")
    con.execute("CREATE TABLE fact_budget_targets AS SELECT * FROM budget")

    con.execute("DROP TABLE IF EXISTS dim_advertisers")
    con.execute("CREATE TABLE dim_advertisers AS SELECT * FROM adv")

    # Save validation to DuckDB too
    con.execute("DROP TABLE IF EXISTS validation_log")
    con.execute("CREATE TABLE validation_log AS SELECT * FROM val_df")

    # Metadata
    con.execute("DROP TABLE IF EXISTS etl_metadata")
    con.execute(f"""
        CREATE TABLE etl_metadata AS
        SELECT
            '{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}' AS last_refresh,
            {len(clean)} AS clean_records,
            {len(quarantine)} AS quarantined_records,
            {quality_score} AS quality_score
    """)

    con.close()
    print(f"✓ ETL complete. {len(clean):,} records loaded to DuckDB.")
    print(f"✓ Data quality score: {quality_score}%")
    return quality_score, validation_results

if __name__ == "__main__":
    run_etl()
