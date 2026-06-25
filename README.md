# AdsPulse: Advertising Strategy & Planning Platform

A strategy and planning platform that mirrors how an advertising operations team runs the business — not just tracking campaign metrics, but managing performance against targets, governing data definitions, and enabling teams to make decisions without waiting for an analyst.

Live App: https://nithink-pixel-adspulse.streamlit.app
GitHub: https://github.com/nithink-pixel/adspulse

---

## Background

Most advertising dashboards I've seen show what happened. This project was built to answer a different set of questions: Are we hitting plan? Where should budget go next quarter? Can we trust the numbers we're looking at?

I built this to understand how a Strategy & Planning function at an advertising organization actually operates — the reporting infrastructure, the governance layer, and the planning tools that sit behind the dashboards.

---

## What It Does

### Tab 1: Executive MBR Dashboard
Monthly business review view tracking revenue vs target by month, ROAS by region, channel performance, and top advertiser breakdown. Filters by region, segment, and quarter. Built to answer: are we on plan, and where are we falling short?

### Tab 2: KPI Governance Center
A single source of truth for every metric — one definition, one formula, one owner, one source table. Built to eliminate the "which number is right?" problem that slows down every cross-functional business review.

### Tab 3: Data Quality Monitor
12 validation rules run on every ETL pass. Records that fail validation are quarantined before they reach a dashboard. Pass rate is tracked per rule and displayed in real time so you always know the reliability of what you're looking at.

### Tab 4: Strategic Planning Center
Revenue forecasting using linear trend modeling, budget allocation scenarios weighted by ROAS, and conservative / base / optimistic scenario analysis. Built for the "what happens if we increase budget by 20%?" conversation.

### Tab 5: Self-Service Analytics
A filter-and-group report builder. No SQL required. Users select dimensions and metrics, view the chart, and export to CSV. Built so non-technical stakeholders can answer their own questions without routing everything through an analyst.

---

## Data Architecture

```
Raw CSVs (synthetic, generated via generate_data.py)
    ↓
ETL Pipeline (Python + 12 validation rules)
    ↓
DuckDB Warehouse (4 fact/dim tables + validation log)
    ↓
Streamlit Dashboard (5 tabs)
```

### Tables
- `fact_campaign_performance` — daily ad performance by advertiser, channel, and region
- `fact_sales_pipeline` — advertiser opportunity pipeline by stage and segment
- `fact_budget_targets` — monthly revenue and spend targets by region
- `dim_advertisers` — advertiser attributes including industry, segment, and region
- `validation_log` — ETL rule results and pass rates per run
- `etl_metadata` — last refresh timestamp, record counts, and quality score

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

## Key Design Decisions

**Why DuckDB?** It runs in-process, requires no server setup, and handles analytical SQL queries on structured CSVs efficiently. Good fit for a self-contained portfolio project.

**Why a KPI governance layer?** Without agreed definitions, every number in a business review gets challenged. The governance center was the most important thing to build — it's what separates a dashboard from a reliable reporting system.

**Why synthetic data?** The dataset was generated to reflect realistic advertising patterns — seasonality, channel mix, advertiser segments, anomalies — without using any real or proprietary information.
