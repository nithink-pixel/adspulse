import streamlit as st
import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
import os

# Resolve paths relative to this file's location
DASH_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(DASH_DIR)
sys.path.insert(0, DASH_DIR)
sys.path.insert(0, os.path.join(BASE_DIR, "data"))
sys.path.insert(0, os.path.join(BASE_DIR, "etl"))

from modules import experiments, attribution, customers, incrementality, exec_brief

KPI_CATALOG = [
    {"kpi": "Revenue", "definition": "Total revenue attributed to ad-driven conversions in the period.", "formula": "SUM(revenue)", "owner": "Ads Finance", "source_table": "fact_campaign_performance", "refresh": "Daily", "status": "✓ Validated", "lineage": "fact_campaign_performance → conversions × avg_order_value"},
    {"kpi": "Spend", "definition": "Total advertising dollars spent across all campaigns in the period.", "formula": "SUM(spend)", "owner": "Ads Finance", "source_table": "fact_campaign_performance", "refresh": "Daily", "status": "✓ Validated", "lineage": "fact_campaign_performance → spend"},
    {"kpi": "ROAS", "definition": "Return on Ad Spend. Revenue generated per dollar of advertising spend. ROAS > 1 = profitable.", "formula": "SUM(revenue) / SUM(spend)", "owner": "Ads Finance", "source_table": "fact_campaign_performance", "refresh": "Daily", "status": "✓ Validated", "lineage": "fact_campaign_performance → revenue / spend"},
    {"kpi": "CTR", "definition": "Click-Through Rate. Percentage of impressions that resulted in a click.", "formula": "SUM(clicks) / SUM(impressions)", "owner": "Marketing Ops", "source_table": "fact_campaign_performance", "refresh": "Daily", "status": "✓ Validated", "lineage": "fact_campaign_performance → clicks / impressions"},
    {"kpi": "CPC", "definition": "Cost Per Click. Average cost paid per user click.", "formula": "SUM(spend) / SUM(clicks)", "owner": "Media Operations", "source_table": "fact_campaign_performance", "refresh": "Daily", "status": "✓ Validated", "lineage": "fact_campaign_performance → spend / clicks"},
    {"kpi": "CPM", "definition": "Cost Per Mille. Cost per 1,000 impressions.", "formula": "SUM(spend) / (SUM(impressions) / 1000)", "owner": "Media Operations", "source_table": "fact_campaign_performance", "refresh": "Daily", "status": "✓ Validated", "lineage": "fact_campaign_performance → spend / (impressions / 1000)"},
    {"kpi": "Conversion Rate", "definition": "Percentage of clicks that resulted in a desired action.", "formula": "SUM(conversions) / SUM(clicks)", "owner": "Growth Analytics", "source_table": "fact_campaign_performance", "refresh": "Daily", "status": "✓ Validated", "lineage": "fact_campaign_performance → conversions / clicks"},
    {"kpi": "CPA", "definition": "Cost Per Acquisition. Average spend required to generate one conversion.", "formula": "SUM(spend) / SUM(conversions)", "owner": "Growth Analytics", "source_table": "fact_campaign_performance", "refresh": "Daily", "status": "✓ Validated", "lineage": "fact_campaign_performance → spend / conversions"},
    {"kpi": "Active Advertisers", "definition": "Count of unique advertisers with at least one campaign record in the period.", "formula": "COUNT(DISTINCT advertiser_id) WHERE spend > 0", "owner": "Sales Strategy", "source_table": "fact_campaign_performance", "refresh": "Daily", "status": "✓ Validated", "lineage": "fact_campaign_performance → DISTINCT advertiser_id"},
    {"kpi": "Pipeline Revenue", "definition": "Total projected revenue across all open sales opportunities.", "formula": "SUM(projected_revenue) WHERE stage NOT IN ('Closed Won','Closed Lost')", "owner": "Sales Strategy", "source_table": "fact_sales_pipeline", "refresh": "Weekly", "status": "✓ Validated", "lineage": "fact_sales_pipeline → projected_revenue"},
    {"kpi": "Revenue vs Target", "definition": "Actual revenue as a percentage of the monthly revenue target set in planning.", "formula": "SUM(actual_revenue) / SUM(target_revenue) × 100", "owner": "Ads Finance", "source_table": "fact_campaign_performance JOIN fact_budget_targets", "refresh": "Daily", "status": "✓ Validated", "lineage": "fact_campaign_performance + fact_budget_targets → revenue / target_revenue"},
    {"kpi": "CAC", "definition": "Customer Acquisition Cost. Total media spend divided by customers acquired in the period.", "formula": "SUM(spend) / COUNT(DISTINCT customer_id)", "owner": "Growth Analytics", "source_table": "fact_campaign_performance + dim_customers", "refresh": "Daily", "status": "✓ Validated", "lineage": "fact_campaign_performance → spend / dim_customers → new customers"},
    {"kpi": "CLV", "definition": "Customer Lifetime Value. Cumulative revenue per customer over the 12-month observation window.", "formula": "SUM(order_revenue) / COUNT(DISTINCT customer_id)", "owner": "Growth Analytics", "source_table": "fact_orders", "refresh": "Daily", "status": "✓ Validated", "lineage": "fact_orders → revenue per customer_id"},
    {"kpi": "LTV/CAC Ratio", "definition": "Value created per dollar of acquisition spend. Benchmark: ≥ 3.0x is healthy.", "formula": "CLV / CAC", "owner": "Ads Finance", "source_table": "fact_orders + fact_campaign_performance", "refresh": "Daily", "status": "✓ Validated", "lineage": "CLV ÷ CAC"},
    {"kpi": "Retention Rate", "definition": "Share of an acquisition cohort placing at least one order N months after acquisition.", "formula": "COUNT(DISTINCT active customers in month N) / cohort size", "owner": "Growth Analytics", "source_table": "fact_orders + dim_customers", "refresh": "Daily", "status": "✓ Validated", "lineage": "fact_orders → cohort_month × months_since"},
    {"kpi": "Experiment Lift", "definition": "Relative change in the primary metric between treatment and control, validated by a two-proportion z-test at α = 0.05.", "formula": "(rate_T − rate_C) / rate_C", "owner": "Experimentation", "source_table": "fact_experiments", "refresh": "Per test", "status": "✓ Validated", "lineage": "fact_experiments → successes / users by variant"},
    {"kpi": "Incremental ROAS", "definition": "Causal revenue per ad dollar, measured via geo-holdout difference-in-differences — not last-click attribution.", "formula": "incremental_revenue / ad_spend", "owner": "Marketing Science", "source_table": "fact_geo_experiment", "refresh": "Per test", "status": "✓ Validated", "lineage": "fact_geo_experiment → DiD lift / spend"},
]

st.set_page_config(
    page_title="AdsPulse — Decision Intelligence Platform",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── Styling ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main { background-color: #0f0f0f; }
    .metric-card {
        background: #1a1a2e;
        border-radius: 10px;
        padding: 16px 20px;
        border-left: 4px solid #06b6d4;
        margin-bottom: 10px;
    }
    .stMetric label { color: #94a3b8 !important; font-size: 13px !important; }
    .stMetric [data-testid="metric-container"] { background: #1e293b; border-radius: 8px; padding: 12px; }
    .section-header { color: #06b6d4; font-size: 16px; font-weight: 600; margin-bottom: 8px; }
    div[data-testid="stTab"] button { font-size: 14px; font-weight: 500; }
</style>
""", unsafe_allow_html=True)

# ── In-memory warehouse ───────────────────────────────────────────────────────
# Built ONCE per app process and cached. No files, no read-only/read-write
# conflicts, no "table already exists" — works identically locally and on
# Streamlit Cloud with zero manual ETL steps.
@st.cache_resource(show_spinner="Building AdsPulse warehouse…")
def get_con():
    import generate_data
    import run_etl
    con = duckdb.connect(":memory:")
    run_etl.load_into(con, generate_data.generate_all())
    return con

@st.cache_data(show_spinner=False)
def query(sql):
    return get_con().execute(sql).df()

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.markdown("# 📡 AdsPulse")
st.sidebar.markdown("**Decision Intelligence Platform**")
st.sidebar.markdown("---")

regions = ["All Regions"] + query("SELECT DISTINCT region FROM fact_campaign_performance ORDER BY region")["region"].tolist()
segments = ["All Segments"] + query("SELECT DISTINCT segment FROM dim_advertisers ORDER BY segment")["segment"].tolist()
quarters = ["All Quarters", "Q1", "Q2", "Q3", "Q4"]

sel_region  = st.sidebar.selectbox("Region",  regions)
sel_segment = st.sidebar.selectbox("Segment", segments)
sel_quarter = st.sidebar.selectbox("Quarter", quarters)

meta = query("SELECT * FROM etl_metadata")
st.sidebar.markdown("---")
st.sidebar.markdown(f"**Last Refresh:** {meta['last_refresh'].iloc[0]}")
st.sidebar.markdown(f"**Data Quality:** {meta['quality_score'].iloc[0]}%")
st.sidebar.markdown(f"**Clean Records:** {int(meta['clean_records'].iloc[0]):,}")

# ── Filters ───────────────────────────────────────────────────────────────────
def build_where(table_prefix=""):
    clauses = []
    p = f"{table_prefix}." if table_prefix else ""
    if sel_region  != "All Regions":  clauses.append(f"{p}region = '{sel_region}'")
    if sel_quarter != "All Quarters": clauses.append(f"{p}quarter = {sel_quarter[1]}")
    return "WHERE " + " AND ".join(clauses) if clauses else ""

# ── TABS ──────────────────────────────────────────────────────────────────────
tab1, tab_exp, tab_attr, tab_cust, tab_incr, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Executive MBR",
    "🧪 Experiments",
    "🧭 Attribution",
    "👥 Customer Analytics",
    "📐 Incrementality",
    "📋 KPI Governance",
    "🔍 Data Quality",
    "📈 Strategic Planning",
    "🔎 Self-Service Analytics"
])

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1: Executive MBR Dashboard
# ─────────────────────────────────────────────────────────────────────────────
with tab1:
    st.markdown("## Executive Monthly Business Review")
    st.markdown("*What leadership sees. Revenue, spend, efficiency, and plan attainment — in one view.*")
    st.markdown("---")

    exec_brief.render(query)
    st.markdown("---")

    w = build_where()
    kpi_df = query(f"""
        SELECT
            SUM(revenue)     AS total_revenue,
            SUM(spend)       AS total_spend,
            SUM(impressions) AS total_impressions,
            SUM(clicks)      AS total_clicks,
            SUM(conversions) AS total_conversions,
            COUNT(DISTINCT advertiser_id) AS active_advertisers,
            SUM(revenue)/NULLIF(SUM(spend),0) AS roas,
            SUM(clicks)/NULLIF(SUM(impressions),0)*100 AS ctr,
            SUM(spend)/NULLIF(SUM(conversions),0) AS cpa
        FROM fact_campaign_performance {w}
    """)

    r = kpi_df.iloc[0]
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Total Revenue",        f"${r['total_revenue']:,.0f}")
    c2.metric("Total Spend",          f"${r['total_spend']:,.0f}")
    c3.metric("ROAS",                 f"{r['roas']:.2f}x")
    c4.metric("Active Advertisers",   f"{int(r['active_advertisers']):,}")
    c5.metric("CTR",                  f"{r['ctr']:.2f}%")

    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Revenue vs Target by Month")
        rev_target = query(f"""
            SELECT
                c.month,
                SUM(c.revenue) AS actual_revenue,
                AVG(b.target_revenue) AS target_revenue
            FROM fact_campaign_performance c
            LEFT JOIN fact_budget_targets b
                ON c.month = b.month
                {"AND c.region = b.region" if sel_region != "All Regions" else ""}
                {"AND c.region = '" + sel_region + "'" if sel_region != "All Regions" else ""}
            {("WHERE c.quarter = " + sel_quarter[1]) if sel_quarter != "All Quarters" else ""}
            GROUP BY c.month ORDER BY c.month
        """)
        fig = go.Figure()
        fig.add_bar(x=rev_target["month"], y=rev_target["actual_revenue"], name="Actual", marker_color="#06b6d4")
        fig.add_scatter(x=rev_target["month"], y=rev_target["target_revenue"], name="Target",
                       mode="lines+markers", line=dict(color="#f59e0b", dash="dash", width=2))
        fig.update_layout(template="plotly_dark", height=320, margin=dict(t=10,b=10))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("#### Revenue by Region")
        reg_df = query(f"""
            SELECT region, SUM(revenue) AS revenue, SUM(spend) AS spend,
                   SUM(revenue)/NULLIF(SUM(spend),0) AS roas
            FROM fact_campaign_performance {w}
            GROUP BY region ORDER BY revenue DESC
        """)
        fig2 = px.bar(reg_df, x="region", y="revenue", color="roas",
                      color_continuous_scale="teal", template="plotly_dark", height=320)
        fig2.update_layout(margin=dict(t=10,b=10))
        st.plotly_chart(fig2, use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        st.markdown("#### Revenue by Channel")
        ch_df = query(f"""
            SELECT channel, SUM(revenue) AS revenue, SUM(spend) AS spend,
                   SUM(revenue)/NULLIF(SUM(spend),0) AS roas
            FROM fact_campaign_performance {w}
            GROUP BY channel ORDER BY revenue DESC
        """)
        fig3 = px.pie(ch_df, names="channel", values="revenue", template="plotly_dark",
                      color_discrete_sequence=px.colors.sequential.Teal, height=300)
        fig3.update_layout(margin=dict(t=10,b=10))
        st.plotly_chart(fig3, use_container_width=True)

    with col4:
        st.markdown("#### Top 10 Advertisers by Revenue")
        top_adv = query(f"""
            SELECT c.advertiser_id, a.segment,
                   SUM(c.revenue) AS revenue,
                   SUM(c.spend)   AS spend,
                   SUM(c.revenue)/NULLIF(SUM(c.spend),0) AS roas
            FROM fact_campaign_performance c
            JOIN dim_advertisers a USING (advertiser_id)
            {("WHERE a.segment = '" + sel_segment + "'") if sel_segment != "All Segments" else ""}
            GROUP BY c.advertiser_id, a.segment
            ORDER BY revenue DESC LIMIT 10
        """)
        fig4 = px.bar(top_adv, x="revenue", y="advertiser_id", orientation="h",
                      color="roas", color_continuous_scale="teal", template="plotly_dark", height=320)
        fig4.update_layout(margin=dict(t=10,b=10))
        st.plotly_chart(fig4, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# NEW MODULES: Experiments / Attribution / Customer Analytics / Incrementality
# ─────────────────────────────────────────────────────────────────────────────
with tab_exp:
    experiments.render(query)

with tab_attr:
    attribution.render(query)

with tab_cust:
    customers.render(query)

with tab_incr:
    incrementality.render(query)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2: KPI Governance Center
# ─────────────────────────────────────────────────────────────────────────────
with tab2:
    st.markdown("## KPI Governance Center")
    st.markdown("*Single source of truth for every metric — definition, owner, source, lineage, and validation status.*")
    st.markdown("---")

    kpi_df_display = pd.DataFrame(KPI_CATALOG)[[
        "kpi", "definition", "formula", "owner", "source_table", "refresh", "status"
    ]]
    kpi_df_display.columns = ["KPI", "Definition", "Formula", "Owner", "Source Table", "Refresh", "Status"]

    st.dataframe(kpi_df_display, use_container_width=True, height=420)

    st.markdown("---")
    st.markdown("#### Metric Lineage")
    selected_kpi = st.selectbox("Select a KPI to view lineage:", [k["kpi"] for k in KPI_CATALOG])
    selected = next(k for k in KPI_CATALOG if k["kpi"] == selected_kpi)

    col1, col2, col3 = st.columns(3)
    col1.markdown(f"**Definition:** {selected['definition']}")
    col2.markdown(f"**Formula:** `{selected['formula']}`")
    col3.markdown(f"**Lineage:** {selected['lineage']}")

    st.info(f"**Owner:** {selected['owner']} | **Source:** `{selected['source_table']}` | **Refresh:** {selected['refresh']} | **Status:** {selected['status']}")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3: Data Quality Monitor
# ─────────────────────────────────────────────────────────────────────────────
with tab3:
    st.markdown("## Data Quality Monitor")
    st.markdown("*17 validation rules enforced on every ETL run across campaign and order data. Bad records quarantined before reaching dashboards.*")
    st.markdown("---")

    meta = query("SELECT * FROM etl_metadata")
    val  = query("SELECT * FROM validation_log")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Data Quality Score",  f"{meta['quality_score'].iloc[0]}%")
    m2.metric("Clean Records",       f"{int(meta['clean_records'].iloc[0]):,}")
    m3.metric("Quarantined Records", f"{int(meta['quarantined_records'].iloc[0]):,}")
    m4.metric("Rules Enforced",      f"{len(val)}")

    st.markdown("---")
    st.markdown("#### Validation Rule Results")

    def color_status(val_str):
        if "PASS" in str(val_str):
            return "background-color: #14532d; color: #86efac"
        return "background-color: #7f1d1d; color: #fca5a5"

    styled = val.style.map(color_status, subset=["status"])
    st.dataframe(styled, use_container_width=True, height=420)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### Pass Rate by Rule")
        fig = px.bar(val, x="rule_id", y="pass_rate", color="pass_rate",
                     color_continuous_scale="RdYlGn", range_color=[95, 100],
                     template="plotly_dark", height=300)
        fig.add_hline(y=99, line_dash="dash", line_color="#f59e0b",
                      annotation_text="99% threshold")
        fig.update_layout(margin=dict(t=10,b=10))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("#### Failed Records by Rule")
        failed = val[val["failed"] > 0]
        if len(failed) > 0:
            fig2 = px.bar(failed, x="rule_id", y="failed", color="failed",
                          color_continuous_scale="Reds", template="plotly_dark", height=300)
            fig2.update_layout(margin=dict(t=10,b=10))
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.success("All rules passed. Zero failed records.")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4: Strategic Planning Center
# ─────────────────────────────────────────────────────────────────────────────
with tab4:
    st.markdown("## Strategic Planning Center")
    st.markdown("*Revenue forecasting, budget allocation scenarios, and go-to-market analysis.*")
    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Q4 Revenue Forecast")
        monthly = query("""
            SELECT month, SUM(revenue) AS revenue, SUM(spend) AS spend
            FROM fact_campaign_performance
            GROUP BY month ORDER BY month
        """)
        # Simple linear trend forecast
        from numpy.polynomial import polynomial as P
        x = monthly["month"].values
        y = monthly["revenue"].values
        coef = P.polyfit(x, y, 1)
        forecast_months = [11, 12]
        forecast_vals = [P.polyval(m, coef) for m in forecast_months]

        fig = go.Figure()
        fig.add_scatter(x=monthly["month"], y=monthly["revenue"],
                       name="Actual", mode="lines+markers",
                       line=dict(color="#06b6d4", width=2))
        fig.add_scatter(x=forecast_months, y=forecast_vals,
                       name="Forecast", mode="lines+markers",
                       line=dict(color="#f59e0b", dash="dash", width=2))
        fig.update_layout(template="plotly_dark", height=300,
                         xaxis_title="Month", yaxis_title="Revenue ($)",
                         margin=dict(t=10,b=10))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("#### Budget Allocation Scenario")
        budget_increase = st.slider("Budget Increase (%)", 0, 100, 20, 5)
        channel_perf = query("""
            SELECT channel,
                   SUM(revenue)/NULLIF(SUM(spend),0) AS roas,
                   SUM(spend) AS current_spend
            FROM fact_campaign_performance
            GROUP BY channel ORDER BY roas DESC
        """)
        total_increase = channel_perf["current_spend"].sum() * (budget_increase / 100)
        # Allocate proportionally to ROAS
        channel_perf["roas_weight"]    = channel_perf["roas"] / channel_perf["roas"].sum()
        channel_perf["additional_spend"] = channel_perf["roas_weight"] * total_increase
        channel_perf["recommended_spend"] = channel_perf["current_spend"] + channel_perf["additional_spend"]
        channel_perf["projected_revenue"] = channel_perf["recommended_spend"] * channel_perf["roas"]

        fig2 = px.bar(channel_perf, x="channel",
                      y=["current_spend", "additional_spend"],
                      template="plotly_dark", barmode="stack",
                      color_discrete_map={"current_spend": "#06b6d4", "additional_spend": "#f59e0b"},
                      height=300)
        fig2.update_layout(margin=dict(t=10,b=10))
        st.plotly_chart(fig2, use_container_width=True)
        st.caption(f"Projected additional revenue from {budget_increase}% budget increase: "
                   f"${channel_perf['additional_spend'].sum() * channel_perf['roas'].mean():,.0f}")

    st.markdown("---")
    st.markdown("#### Scenario Analysis")
    base_revenue = query("SELECT SUM(revenue) AS r FROM fact_campaign_performance")["r"].iloc[0]
    sc1, sc2, sc3 = st.columns(3)
    sc1.metric("Conservative (-10%)", f"${base_revenue * 0.90:,.0f}", "-10%")
    sc2.metric("Base Case",           f"${base_revenue:,.0f}",         "Actual")
    sc3.metric("Optimistic (+20%)",   f"${base_revenue * 1.20:,.0f}", "+20%")

    st.markdown("---")
    st.markdown("#### Segment Growth Analysis")
    seg_df = query("""
        SELECT a.segment,
               SUM(c.revenue) AS revenue,
               SUM(c.spend)   AS spend,
               COUNT(DISTINCT c.advertiser_id) AS advertisers,
               SUM(c.revenue)/NULLIF(SUM(c.spend),0) AS roas
        FROM fact_campaign_performance c
        JOIN dim_advertisers a USING (advertiser_id)
        GROUP BY a.segment ORDER BY revenue DESC
    """)
    fig3 = px.scatter(seg_df, x="spend", y="revenue", size="advertisers",
                      color="segment", text="segment",
                      template="plotly_dark", height=320)
    fig3.update_layout(margin=dict(t=10,b=10))
    st.plotly_chart(fig3, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5: Self-Service Analytics
# ─────────────────────────────────────────────────────────────────────────────
with tab5:
    st.markdown("## Self-Service Analytics")
    st.markdown("*Build your own report — no SQL required. Filter, group, and export.*")
    st.markdown("---")

    col1, col2, col3, col4 = st.columns(4)
    ss_region   = col1.multiselect("Region",   REGION_OPTS   := query("SELECT DISTINCT region FROM fact_campaign_performance")["region"].tolist(),  default=None)
    ss_channel  = col2.multiselect("Channel",  CHANNEL_OPTS  := query("SELECT DISTINCT channel FROM fact_campaign_performance")["channel"].tolist(), default=None)
    ss_segment  = col3.multiselect("Segment",  SEGMENT_OPTS  := query("SELECT DISTINCT segment FROM dim_advertisers")["segment"].tolist(),           default=None)
    ss_groupby  = col4.selectbox("Group By",   ["channel", "region", "segment", "month", "quarter"])

    clauses = []
    if ss_region:  clauses.append(f"c.region  IN ({','.join([repr(r) for r in ss_region])})")
    if ss_channel: clauses.append(f"c.channel IN ({','.join([repr(r) for r in ss_channel])})")
    if ss_segment: clauses.append(f"a.segment IN ({','.join([repr(r) for r in ss_segment])})")
    where = "WHERE " + " AND ".join(clauses) if clauses else ""

    group_col = ss_groupby if ss_groupby not in ["segment"] else "a.segment"
    if ss_groupby == "segment":
        select_col = "a.segment AS segment"
    elif ss_groupby == "month":
        select_col = "c.month"
    elif ss_groupby == "quarter":
        select_col = "c.quarter"
    else:
        select_col = f"c.{ss_groupby}"

    ss_df = query(f"""
        SELECT {select_col},
               SUM(c.revenue)     AS revenue,
               SUM(c.spend)       AS spend,
               SUM(c.impressions) AS impressions,
               SUM(c.clicks)      AS clicks,
               SUM(c.conversions) AS conversions,
               SUM(c.revenue)/NULLIF(SUM(c.spend),0)       AS roas,
               SUM(c.clicks)/NULLIF(SUM(c.impressions),0)  AS ctr,
               SUM(c.spend)/NULLIF(SUM(c.conversions),0)   AS cpa
        FROM fact_campaign_performance c
        JOIN dim_advertisers a USING (advertiser_id)
        {where}
        GROUP BY {select_col if 'AS' not in select_col else select_col.split(' AS ')[1]}
        ORDER BY revenue DESC
    """)

    metric_choice = st.selectbox("Visualize:", ["revenue", "spend", "roas", "ctr", "cpa"])
    fig = px.bar(ss_df, x=ss_groupby, y=metric_choice,
                 color=metric_choice, color_continuous_scale="teal",
                 template="plotly_dark", height=320)
    fig.update_layout(margin=dict(t=10,b=10))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Raw Data")
    st.dataframe(ss_df.style.format({
        "revenue": "${:,.0f}", "spend": "${:,.0f}",
        "roas": "{:.2f}x", "ctr": "{:.3f}", "cpa": "${:.2f}"
    }), use_container_width=True)

    csv = ss_df.to_csv(index=False)
    st.download_button("⬇ Export to CSV", csv, "ads_strategy_report.csv", "text/csv")
