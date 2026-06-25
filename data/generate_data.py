import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

np.random.seed(42)

# ── Config ────────────────────────────────────────────────────────────────────
REGIONS     = ["North America", "EMEA", "APAC", "LATAM"]
SEGMENTS    = ["Enterprise", "Mid-Market", "SMB"]
INDUSTRIES  = ["E-Commerce", "Travel", "Finance", "Retail", "Tech", "Healthcare", "Auto", "Media"]
CHANNELS    = ["Search", "Display", "Social", "Video", "Native"]
STAGES      = ["Prospecting", "Qualified", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]
N_ADVERTISERS = 80
START = datetime(2024, 1, 1)
END   = datetime(2024, 12, 31)

os.makedirs("data/raw", exist_ok=True)

# ── dim_advertisers ───────────────────────────────────────────────────────────
advertisers = pd.DataFrame({
    "advertiser_id":   [f"ADV{str(i).zfill(3)}" for i in range(1, N_ADVERTISERS + 1)],
    "advertiser_name": [f"Advertiser_{i}"         for i in range(1, N_ADVERTISERS + 1)],
    "industry":        np.random.choice(INDUSTRIES, N_ADVERTISERS),
    "segment":         np.random.choice(SEGMENTS,   N_ADVERTISERS, p=[0.2, 0.3, 0.5]),
    "region":          np.random.choice(REGIONS,    N_ADVERTISERS),
    "account_owner":   [f"AE_{np.random.randint(1, 12)}" for _ in range(N_ADVERTISERS)],
    "start_date":      [(START + timedelta(days=int(np.random.randint(0, 180)))).strftime("%Y-%m-%d")
                        for _ in range(N_ADVERTISERS)],
})
advertisers.to_csv("data/raw/dim_advertisers.csv", index=False)
print(f"dim_advertisers: {len(advertisers)} rows")

# ── fact_campaign_performance ─────────────────────────────────────────────────
records = []
dates = pd.date_range(START, END, freq="D")

for _, adv in advertisers.iterrows():
    channel        = np.random.choice(CHANNELS)
    base_spend     = np.random.uniform(200, 8000)
    base_impr      = np.random.uniform(5000, 150000)
    base_ctr       = np.random.uniform(0.01, 0.06)
    base_conv_rate = np.random.uniform(0.02, 0.09)

    for date in dates:
        # Skip ~40% of days (advertisers don't run every day)
        if np.random.random() < 0.40:
            continue

        seasonal = 1.0
        if date.month in [11, 12]: seasonal = 1.45
        elif date.month in [6, 7]: seasonal = 1.15
        elif date.month in [1, 2]: seasonal = 0.78

        noise   = np.random.normal(1.0, 0.18)
        spend   = max(0, base_spend * seasonal * noise)
        impr    = max(0, int(base_impr * seasonal * noise))
        clicks  = max(0, int(impr * base_ctr * np.random.normal(1.0, 0.12)))
        convs   = max(0, int(clicks * base_conv_rate * np.random.normal(1.0, 0.12)))
        revenue = convs * np.random.uniform(20, 180)

        # Inject anomalies (~2%)
        if np.random.random() < 0.02: spend   *= np.random.uniform(3, 5)
        if np.random.random() < 0.015: clicks  = 0
        if np.random.random() < 0.01:  spend   = -abs(spend)   # negative spend anomaly

        records.append({
            "date":           date.strftime("%Y-%m-%d"),
            "advertiser_id":  adv["advertiser_id"],
            "campaign_id":    f"CMP{np.random.randint(1000, 9999)}",
            "channel":        channel,
            "region":         adv["region"],
            "impressions":    impr,
            "clicks":         clicks,
            "spend":          round(spend, 2),
            "conversions":    convs,
            "revenue":        round(revenue, 2),
        })

perf = pd.DataFrame(records)
perf.to_csv("data/raw/fact_campaign_performance.csv", index=False)
print(f"fact_campaign_performance: {len(perf)} rows")

# ── fact_sales_pipeline ───────────────────────────────────────────────────────
pipeline_rows = []
for _, adv in advertisers.iterrows():
    n_opps = np.random.randint(1, 5)
    for _ in range(n_opps):
        stage = np.random.choice(STAGES, p=[0.2, 0.2, 0.2, 0.1, 0.2, 0.1])
        pipeline_rows.append({
            "advertiser_id":      adv["advertiser_id"],
            "account_owner":      adv["account_owner"],
            "opportunity_stage":  stage,
            "projected_revenue":  round(np.random.uniform(5000, 500000), 2),
            "close_date":         (START + timedelta(days=int(np.random.randint(30, 365)))).strftime("%Y-%m-%d"),
            "region":             adv["region"],
            "segment":            adv["segment"],
        })
pipeline = pd.DataFrame(pipeline_rows)
pipeline.to_csv("data/raw/fact_sales_pipeline.csv", index=False)
print(f"fact_sales_pipeline: {len(pipeline)} rows")

# ── fact_budget_targets ───────────────────────────────────────────────────────
budget_rows = []
for month in range(1, 13):
    for region in REGIONS:
        budget_rows.append({
            "month":          month,
            "year":           2024,
            "region":         region,
            "target_revenue": round(np.random.uniform(800000, 2500000), 2),
            "target_spend":   round(np.random.uniform(200000, 800000), 2),
            "target_roas":    round(np.random.uniform(2.5, 5.0), 2),
        })
budget = pd.DataFrame(budget_rows)
budget.to_csv("data/raw/fact_budget_targets.csv", index=False)
print(f"fact_budget_targets: {len(budget)} rows")

print("\n✓ All raw data generated.")
