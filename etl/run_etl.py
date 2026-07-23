"""ETL + validation for AdsPulse.

`build_tables(raw)` validates, quarantines, computes KPIs, and returns
warehouse-ready tables entirely in memory (no files, no DB locks). Run directly
to also persist a DuckDB file for local inspection.
"""
import pandas as pd
import numpy as np
from datetime import datetime

DB_PATH = "data/adspulse.duckdb"


def _apply_rules(df, rules, dataset):
    results, quarantine_mask = [], pd.Series([False] * len(df))
    for rule_id, rule_name, mask in rules:
        failed = int(mask.sum())
        results.append({
            "dataset": dataset, "rule_id": rule_id, "rule": rule_name,
            "passed": len(df) - failed, "failed": failed,
            "pass_rate": round((len(df) - failed) / len(df) * 100, 2),
            "status": "✓ PASS" if failed == 0 else "✗ FAIL",
        })
        quarantine_mask |= mask
    return results, quarantine_mask


def validate_campaign(df):
    rules = [
        ("R01", "No negative spend",             df["spend"] < 0),
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
    return _apply_rules(df, rules, "campaign")


def validate_orders(df):
    dup = df.duplicated(subset=["order_id"], keep="first")
    rules = [
        ("O01", "Revenue > 0",             df["revenue"] <= 0),
        ("O02", "No null customer_id",     df["customer_id"].isnull()),
        ("O03", "No duplicate order_id",   dup),
        ("O04", "Order date within range", ~pd.to_datetime(df["order_date"]).between("2024-01-01", "2024-12-31")),
        ("O05", "Order number >= 1",       df["order_number"] < 1),
    ]
    return _apply_rules(df, rules, "orders")


def compute_kpis(df):
    df = df.copy()
    eps = 1e-9
    df["ctr"]             = (df["clicks"]      / (df["impressions"] + eps)).round(4)
    df["cpc"]             = (df["spend"]       / (df["clicks"]      + eps)).round(2)
    df["cpm"]             = (df["spend"]       / ((df["impressions"] / 1000) + eps)).round(2)
    df["conversion_rate"] = (df["conversions"] / (df["clicks"]      + eps)).round(4)
    df["roas"]            = (df["revenue"]     / (df["spend"]       + eps)).round(2)
    df["cpa"]             = (df["spend"]       / (df["conversions"] + eps)).round(2)
    df["month"]           = pd.to_datetime(df["date"]).dt.month
    df["quarter"]         = pd.to_datetime(df["date"]).dt.quarter
    df["year"]            = pd.to_datetime(df["date"]).dt.year
    return df


def build_tables(raw: dict):
    """Return (tables: dict[str, DataFrame], validation_log, metadata)."""
    perf, orders = raw["fact_campaign_performance"], raw["fact_orders"]

    camp_results, camp_bad = validate_campaign(perf)
    ord_results, ord_bad   = validate_orders(orders)
    validation_log = pd.DataFrame(camp_results + ord_results)

    clean = compute_kpis(perf[~camp_bad].copy())
    orders_clean = orders[~ord_bad].copy()
    quarantined = int(camp_bad.sum() + ord_bad.sum())
    quality = round((len(clean) + len(orders_clean)) / (len(perf) + len(orders)) * 100, 2)

    tables = {
        "fact_campaign_performance": clean,
        "fact_sales_pipeline":       raw["fact_sales_pipeline"],
        "fact_budget_targets":       raw["fact_budget_targets"],
        "dim_advertisers":           raw["dim_advertisers"],
        "dim_customers":             raw["dim_customers"],
        "fact_touchpoints":          raw["fact_touchpoints"],
        "fact_orders":               orders_clean,
        "fact_experiments":          raw["fact_experiments"],
        "fact_geo_experiment":       raw["fact_geo_experiment"],
    }
    metadata = pd.DataFrame([{
        "last_refresh": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "clean_records": len(clean), "quarantined_records": quarantined,
        "quality_score": quality,
    }])
    return tables, validation_log, metadata


def load_into(con, raw: dict):
    """Build all tables inside an existing DuckDB connection (in-memory or file)."""
    tables, validation_log, metadata = build_tables(raw)
    for name, df in tables.items():
        con.register("_stg", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _stg")
        con.unregister("_stg")
    con.register("_vlog", validation_log)
    con.execute("CREATE OR REPLACE TABLE validation_log AS SELECT * FROM _vlog")
    con.unregister("_vlog")
    con.register("_meta", metadata)
    con.execute("CREATE OR REPLACE TABLE etl_metadata AS SELECT * FROM _meta")
    con.unregister("_meta")
    return metadata["quality_score"].iloc[0]


if __name__ == "__main__":
    import os, duckdb
    from importlib import import_module
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
    generate_data = import_module("generate_data")

    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Generating + running ETL...")
    raw = generate_data.generate_all()
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = duckdb.connect(DB_PATH)
    score = load_into(con, raw)
    con.close()
    print(f"✓ ETL complete. Data quality score: {score}%")
    print(f"✓ Warehouse written to {DB_PATH}")
