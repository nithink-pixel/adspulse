# AdsPulse: Uber Ads Strategy Review OS

An advertising strategy and planning platform built to mirror how a Strategy & Planning team at a company like Uber Advertising would run their business — covering MBR/QBR reporting, KPI governance, data quality monitoring, revenue forecasting, and self-service analytics.

## What This Is

Most advertising dashboards show campaign metrics. This shows how the business is performing against plan, where investment should go, and whether the data driving those decisions can be trusted.

Built in five days as a portfolio project. Everything is documented, validated, and deployed.

**Live App:** [adspulse.streamlit.app](https://adspulse.streamlit.app)

---

## What It Does

### Tab 1: Executive MBR Dashboard
What leadership sees in a monthly business review. Revenue vs target by month, ROAS by region, top advertisers, channel performance. Filters by region, segment, and quarter.

### Tab 2: KPI Governance Center
Single source of truth for every metric. One definition, one formula, one owner, one source table, one lineage path. Eliminates the "which number is right?" problem in cross-functional reviews.

### Tab 3: Data Quality Monitor
12 validation rules enforced on every ETL run. Bad records quarantined before they reach a dashboard. Pass rate tracked by rule. Data quality score displayed in real time.

### Tab 4: Strategic Planning Center
Revenue forecasting (linear trend), budget allocation scenarios (ROAS-weighted distribution), and scenario analysis (conservative / base / optimistic). Built for the "what if we increase budget by 20%?" conversation.

### Tab 5: Self-Service Analytics
Multi-filter, multi-group report builder. No SQL required. Users pick their dimensions and metrics, see the chart, and download to CSV. Built so non-technical stakeholders can answer their own questions.

---

## Data Architecture

```
Raw CSVs (generated)
    ↓
ETL Pipeline (Python + 12 validation rules)
    ↓
DuckDB Warehouse
    ↓
Streamlit Dashboard (5 tabs)
```

### Tables
- `fact_campaign_performance` — daily ad performance by advertiser, channel, region
- `fact_sales_pipeline` — advertiser opportunity pipeline by stage and segment  
- `fact_budget_targets` — monthly revenue and spend targets by region
- `dim_advertisers` — advertiser attributes (industry, segment, region)
- `validation_log` — ETL rule results and pass rates per run
- `etl_metadata` — last refresh time, record counts, quality score

### KPIs Tracked
Revenue, Spend, ROAS, CTR, CPC, CPM, Conversion Rate, CPA, Active Advertisers, Pipeline Revenue, Revenue vs Target

---

## Local Setup

```bash
pip install -r requirements.txt
cd data && python generate_data.py
cd ../etl && python run_etl.py
cd .. && streamlit run dashboard/app.py
```

---

## Tech Stack

| Layer | Tool |
|---|---|
| Data Warehouse | DuckDB |
| ETL & Validation | Python (Pandas) |
| Dashboard | Streamlit + Plotly |
| Version Control | Git / GitHub |

---

## Why I Built This

I was exploring how a Strategy & Planning team at an advertising-focused company would actually operate — not just tracking campaign metrics, but running the business. That meant MBR reporting, KPI governance, data quality infrastructure, and planning tools, not just a dashboard.

The KPI governance layer was the most interesting part to build. Every metric needs one definition that everyone agrees on. Without that, every business review becomes an argument about whose number is right.
