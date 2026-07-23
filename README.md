# AdsPulse — Decision Intelligence Platform for Marketing Organizations

AdsPulse combines campaign analytics, A/B experimentation, multi-touch attribution, cohort & lifetime-value analysis, incrementality measurement, KPI governance, and auto-generated executive recommendations in one platform — built to answer the questions a marketing leadership team actually asks, not just display what happened.

**Live App:** [https://nithink-pixel-adspulse.streamlit.app](https://adspulse-nithinpixel.streamlit.app/)
**GitHub:** https://github.com/nithink-pixel/adspulse

## Why This Exists

Most advertising dashboards show *what happened*. AdsPulse is built to answer harder questions:

- Are we hitting plan, and will we by year-end? → **Executive MBR + Forecasting**
- Did that creative change actually work? → **Experiment Center**
- Which channel deserves credit for this conversion? → **Attribution Modeling**
- Are the customers we're buying worth what we pay for them? → **Customer Analytics (CLV, cohorts)**
- Did advertising *cause* revenue, or just coincide with it? → **Incrementality**
- Can we trust the numbers on this screen? → **Data Quality + KPI Governance**

## Platform Architecture

```
                     AdsPulse Decision Platform
                    ┌────────────────────────────┐
                    │  Executive Command Center  │
                    │  (MBR + auto-gen brief)    │
                    └─────────────┬──────────────┘
      ┌──────────┬───────────┬───┴────────┬────────────┬───────────┐
      │          │           │            │            │           │
  Experiment  Attribution  Customer   Incrementality  Planning  Governance
  Center      Modeling     Analytics  (geo holdout)   & Forecast & Quality
      │          │           │            │            │           │
      └──────────┴───────────┴────┬───────┴────────────┴───────────┘
                                  │
                       DuckDB Warehouse (10 tables)
                                  │
                    ETL + 17-rule Validation Framework
                                  │
                        Raw data (synthetic CSVs)
```

## Modules

### 1. Executive MBR + Auto-Generated Brief
Monthly business review: revenue vs target, ROAS by region, channel mix, top advertisers. A rule-based decision engine generates the executive brief on every refresh — plan attainment, biggest efficiency gap, biggest risk, and a quantified budget reallocation recommendation with expected incremental revenue.

### 2. Experiment Center
A/B test readouts with real statistical inference: two-proportion z-tests, p-values, 95% confidence intervals on lift, post-hoc power analysis, and a pre-test sample size calculator. Includes a portfolio view of all experiments with ship / no-ship / inconclusive decisions — including a test where treatment *lost* and several that were correctly inconclusive.

### 3. Attribution Modeling
Five multi-touch attribution models (first-touch, last-touch, linear, time-decay, position-based) computed over 18K customer touchpoints. Model comparison shows exactly where the choice of model changes budget conclusions, plus a journey explorer that splits credit for individual customer paths.

### 4. Customer Analytics — Cohorts & CLV
Cohort retention heatmap by acquisition month, retention curves by acquisition channel, and full unit economics: CLV, CAC, LTV/CAC ratio, payback period, AOV, and repeat rate. Answers whether media spend is buying durable customers or one-time buyers.

### 5. Incrementality Analysis
Geo-holdout experiment (30 test geos, 10 holdout) analyzed with difference-in-differences: observed vs counterfactual revenue, incremental ROAS, and a t-test on geo-level lift. Demonstrates why last-click ROAS systematically overstates advertising impact.

### 6. KPI Governance Center
Single source of truth for 17 metrics — one definition, one formula, one owner, one source table, one lineage path. Eliminates the "which number is right?" problem in cross-functional reviews.

### 7. Data Quality Monitor
17 validation rules across campaign and order data run on every ETL pass. Failing records are quarantined before reaching any dashboard; pass rates tracked per rule.

### 8. Strategic Planning Center
Linear-trend revenue forecasting, ROAS-weighted budget allocation scenarios, and conservative / base / optimistic scenario analysis.

### 9. Self-Service Analytics
Filter-and-group report builder with CSV export. No SQL required.

## Data Warehouse

| Table | Grain | Used by |
|---|---|---|
| `fact_campaign_performance` | advertiser × campaign × day | MBR, Planning, Self-Service |
| `fact_orders` | order | Cohorts, CLV |
| `fact_touchpoints` | customer × touch | Attribution |
| `fact_experiments` | experiment × variant × day | Experiment Center |
| `fact_geo_experiment` | geo × week | Incrementality |
| `fact_sales_pipeline` | opportunity | MBR |
| `fact_budget_targets` | region × month | MBR, Planning |
| `dim_advertisers` | advertiser | joins |
| `dim_customers` | customer | Cohorts, CLV, Attribution |
| `validation_log` / `etl_metadata` | rule / run | Data Quality |

## Statistical Methods

Two-proportion z-tests, confidence intervals, statistical power & sample size calculation (Experiment Center) · rule-based multi-touch attribution with exponential time decay (Attribution) · survival-style cohort retention (Customer Analytics) · difference-in-differences causal inference with Welch's t-test (Incrementality) · linear trend regression (Forecasting).

## Local Setup

```bash
pip install -r requirements.txt
python data/generate_data.py
python etl/run_etl.py
streamlit run dashboard/app.py
```

## Tech Stack

| Layer | Tool |
|---|---|
| Data Warehouse | DuckDB |
| ETL & Validation | Python (Pandas) |
| Statistics | SciPy / NumPy |
| Dashboard | Streamlit + Plotly |
| Version Control | Git / GitHub |

## Key Design Decisions

**Why DuckDB?** In-process, zero server setup, fast analytical SQL over structured data — right-sized for a self-contained platform.

**Why a KPI governance layer?** Without agreed definitions, every number in a business review gets challenged. Governance is what separates a dashboard from a reporting system people trust.

**Why measure incrementality separately from ROAS?** Attributed revenue answers "what came with ads"; only a holdout experiment answers "what came *because of* ads." The two diverge, and budget decisions made on the wrong one over-invest in demand-harvesting channels.

**Why synthetic data?** Generated to reflect realistic advertising behavior — seasonality, channel-specific retention, true experiment effects (including a negative one), organic geo trends, and injected data anomalies — without using any real or proprietary information. Because true effects are known by construction, the statistical methods can be verified against ground truth.
