"""Synthetic data generation for AdsPulse.

Exposes `generate_all()` -> dict[str, DataFrame] so the app can build an
in-memory warehouse with no files. Run directly to also write CSVs to data/raw/.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

# ── Config ────────────────────────────────────────────────────────────────────
REGIONS    = ["North America", "EMEA", "APAC", "LATAM"]
SEGMENTS   = ["Enterprise", "Mid-Market", "SMB"]
INDUSTRIES = ["E-Commerce", "Travel", "Finance", "Retail", "Tech", "Healthcare", "Auto", "Media"]
CHANNELS   = ["Search", "Display", "Social", "Video", "Native"]
STAGES     = ["Prospecting", "Qualified", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]
N_ADVERTISERS = 80
N_CUSTOMERS   = 6000
START = datetime(2024, 1, 1)
END   = datetime(2024, 12, 31)

JOURNEY_CHANNELS = ["Search", "Display", "Social", "Video", "Native", "Email"]
# channel -> (acquisition_share, aov_multiplier, retention_multiplier)
CHANNEL_PROFILE = {
    "Search":  (0.30, 1.15, 1.20),
    "Social":  (0.25, 0.90, 0.85),
    "Display": (0.15, 0.85, 0.80),
    "Video":   (0.12, 1.00, 1.00),
    "Native":  (0.08, 0.95, 0.90),
    "Email":   (0.10, 1.10, 1.30),
}
SEG_AOV = {"Consumer": 65, "Prosumer": 140, "Business": 320}

# A/B experiments: (id, name, channel, metric, base_rate, TRUE_lift, days)
EXPERIMENTS = [
    ("EXP001", "Headline copy test — Search ads",      "Search",  "CTR",             0.032, 0.18,  28),
    ("EXP002", "Carousel vs static creative — Social", "Social",  "CTR",             0.041, 0.09,  21),
    ("EXP003", "Landing page redesign",                "Search",  "Conversion Rate", 0.055, 0.14,  28),
    ("EXP004", "Auto-bidding vs manual bidding",       "Display", "Conversion Rate", 0.038, 0.02,  35),
    ("EXP005", "Short-form vs long-form video",        "Video",   "CTR",             0.027, -0.07, 21),
    ("EXP006", "Discount banner on checkout",          "Social",  "Conversion Rate", 0.049, 0.05,  14),
]


def _advertisers():
    return pd.DataFrame({
        "advertiser_id":   [f"ADV{str(i).zfill(3)}" for i in range(1, N_ADVERTISERS + 1)],
        "advertiser_name": [f"Advertiser_{i}" for i in range(1, N_ADVERTISERS + 1)],
        "industry":        np.random.choice(INDUSTRIES, N_ADVERTISERS),
        "segment":         np.random.choice(SEGMENTS, N_ADVERTISERS, p=[0.2, 0.3, 0.5]),
        "region":          np.random.choice(REGIONS, N_ADVERTISERS),
        "account_owner":   [f"AE_{np.random.randint(1, 12)}" for _ in range(N_ADVERTISERS)],
        "start_date":      [(START + timedelta(days=int(np.random.randint(0, 180)))).strftime("%Y-%m-%d")
                            for _ in range(N_ADVERTISERS)],
    })


def _campaign_performance(advertisers):
    records = []
    dates = pd.date_range(START, END, freq="D")
    for _, adv in advertisers.iterrows():
        channel        = np.random.choice(CHANNELS)
        base_spend     = np.random.uniform(200, 8000)
        base_impr      = np.random.uniform(5000, 150000)
        base_ctr       = np.random.uniform(0.01, 0.06)
        base_conv_rate = np.random.uniform(0.02, 0.09)
        for date in dates:
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
            if np.random.random() < 0.02:  spend  *= np.random.uniform(3, 5)
            if np.random.random() < 0.015: clicks  = 0
            if np.random.random() < 0.01:  spend   = -abs(spend)
            records.append({
                "date": date.strftime("%Y-%m-%d"), "advertiser_id": adv["advertiser_id"],
                "campaign_id": f"CMP{np.random.randint(1000, 9999)}", "channel": channel,
                "region": adv["region"], "impressions": impr, "clicks": clicks,
                "spend": round(spend, 2), "conversions": convs, "revenue": round(revenue, 2),
            })
    return pd.DataFrame(records)


def _pipeline(advertisers):
    rows = []
    for _, adv in advertisers.iterrows():
        for _ in range(np.random.randint(1, 5)):
            rows.append({
                "advertiser_id": adv["advertiser_id"], "account_owner": adv["account_owner"],
                "opportunity_stage": np.random.choice(STAGES, p=[0.2, 0.2, 0.2, 0.1, 0.2, 0.1]),
                "projected_revenue": round(np.random.uniform(5000, 500000), 2),
                "close_date": (START + timedelta(days=int(np.random.randint(30, 365)))).strftime("%Y-%m-%d"),
                "region": adv["region"], "segment": adv["segment"],
            })
    return pd.DataFrame(rows)


def _budget():
    rows = []
    for month in range(1, 13):
        for region in REGIONS:
            rows.append({
                "month": month, "year": 2024, "region": region,
                "target_revenue": round(np.random.uniform(800000, 2500000), 2),
                "target_spend": round(np.random.uniform(200000, 800000), 2),
                "target_roas": round(np.random.uniform(2.5, 5.0), 2),
            })
    return pd.DataFrame(rows)


def _customers():
    acq = np.random.choice(list(CHANNEL_PROFILE), N_CUSTOMERS,
                           p=[CHANNEL_PROFILE[c][0] for c in CHANNEL_PROFILE])
    return pd.DataFrame({
        "customer_id":         [f"CUST{str(i).zfill(5)}" for i in range(1, N_CUSTOMERS + 1)],
        "acquisition_date":    [(START + timedelta(days=int(np.random.randint(0, 300)))).strftime("%Y-%m-%d")
                                for _ in range(N_CUSTOMERS)],
        "acquisition_channel": acq,
        "region":              np.random.choice(REGIONS, N_CUSTOMERS, p=[0.4, 0.25, 0.2, 0.15]),
        "segment":             np.random.choice(["Consumer", "Prosumer", "Business"], N_CUSTOMERS, p=[0.6, 0.25, 0.15]),
    })


def _touchpoints(customers):
    rows = []
    for _, c in customers.iterrows():
        acq_date = datetime.strptime(c["acquisition_date"], "%Y-%m-%d")
        n = np.random.choice([1, 2, 3, 4, 5, 6], p=[0.15, 0.25, 0.25, 0.18, 0.10, 0.07])
        journey_days = np.sort(np.random.randint(0, 21, n - 1)) if n > 1 else []
        channels = list(np.random.choice(JOURNEY_CHANNELS, n - 1,
                        p=[0.15, 0.25, 0.25, 0.15, 0.10, 0.10])) + [c["acquisition_channel"]]
        for i, ch in enumerate(channels):
            offset = 0 if i == n - 1 else int(journey_days[i]) - 21
            rows.append({
                "customer_id": c["customer_id"], "touch_number": i + 1, "total_touches": n,
                "channel": ch, "touch_date": (acq_date + timedelta(days=offset)).strftime("%Y-%m-%d"),
                "converted": 1,
            })
    return pd.DataFrame(rows)


def _orders(customers):
    rows, oid = [], 1
    for _, c in customers.iterrows():
        acq_date = datetime.strptime(c["acquisition_date"], "%Y-%m-%d")
        aov_base = SEG_AOV[c["segment"]] * CHANNEL_PROFILE[c["acquisition_channel"]][1]
        retention = CHANNEL_PROFILE[c["acquisition_channel"]][2]
        rows.append({"order_id": f"ORD{str(oid).zfill(6)}", "customer_id": c["customer_id"],
                     "order_date": c["acquisition_date"],
                     "revenue": round(max(10, np.random.normal(aov_base, aov_base * 0.3)), 2), "order_number": 1})
        oid += 1
        month, p_repeat, num = 1, 0.42 * retention, 2
        while True:
            order_dt = acq_date + timedelta(days=int(month * 30 + np.random.randint(-10, 10)))
            if order_dt > END or np.random.random() > p_repeat:
                break
            rows.append({"order_id": f"ORD{str(oid).zfill(6)}", "customer_id": c["customer_id"],
                         "order_date": order_dt.strftime("%Y-%m-%d"),
                         "revenue": round(max(10, np.random.normal(aov_base, aov_base * 0.25)), 2), "order_number": num})
            oid += 1; num += 1; month += 1; p_repeat *= 0.88
    return pd.DataFrame(rows)


def _experiments():
    rows = []
    for exp_id, name, channel, metric, base_rate, true_lift, days in EXPERIMENTS:
        start_offset = np.random.randint(60, 240)
        for day in range(days):
            d = (START + timedelta(days=start_offset + day)).strftime("%Y-%m-%d")
            for variant, rate in [("Control", base_rate), ("Treatment", base_rate * (1 + true_lift))]:
                users = int(np.random.uniform(1500, 3500))
                successes = np.random.binomial(users, min(0.99, max(0.001, rate * np.random.normal(1, 0.05))))
                rows.append({"experiment_id": exp_id, "experiment_name": name, "channel": channel,
                             "primary_metric": metric, "date": d, "variant": variant,
                             "users": users, "successes": successes,
                             "revenue": round(successes * np.random.uniform(40, 90), 2)})
    return pd.DataFrame(rows)


def _geo_experiment():
    rows, N_GEOS, TEST_START_WEEK = [], 40, 8
    for g in range(1, N_GEOS + 1):
        is_holdout = g > 30
        base = np.random.uniform(40000, 120000)
        trend = np.random.uniform(0.999, 1.004)
        for week in range(16):
            seasonal = 1 + 0.06 * np.sin(week / 2.5)
            lift, spend = 1.0, 0.0
            if week >= TEST_START_WEEK and not is_holdout:
                lift = np.random.normal(1.19, 0.03)
                spend = base * np.random.uniform(0.06, 0.09)
            rows.append({"geo_id": f"GEO{str(g).zfill(2)}",
                         "geo_group": "Holdout (no ads)" if is_holdout else "Test (ads on)",
                         "week": week, "period": "Pre" if week < TEST_START_WEEK else "Test",
                         "revenue": round(base * (trend ** week) * seasonal * lift * np.random.normal(1, 0.04), 2),
                         "ad_spend": round(spend, 2)})
    return pd.DataFrame(rows)


def generate_all(seed: int = 42) -> dict:
    """Return every raw table as a DataFrame. Deterministic given `seed`."""
    np.random.seed(seed)
    advertisers = _advertisers()
    customers = _customers()
    return {
        "dim_advertisers":            advertisers,
        "fact_campaign_performance":  _campaign_performance(advertisers),
        "fact_sales_pipeline":        _pipeline(advertisers),
        "fact_budget_targets":        _budget(),
        "dim_customers":              customers,
        "fact_touchpoints":           _touchpoints(customers),
        "fact_orders":                _orders(customers),
        "fact_experiments":           _experiments(),
        "fact_geo_experiment":        _geo_experiment(),
    }


if __name__ == "__main__":
    os.makedirs("data/raw", exist_ok=True)
    tables = generate_all()
    for name, df in tables.items():
        df.to_csv(f"data/raw/{name}.csv", index=False)
        print(f"{name}: {len(df):,} rows")
    print("\n✓ All raw data written to data/raw/")
