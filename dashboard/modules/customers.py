"""Customer Analytics — cohort retention and customer lifetime value.

- Cohort analysis: retention by acquisition month, months since acquisition
- Unit economics: CLV, CAC, LTV/CAC ratio, payback period, AOV, repeat rate
- Channel-level economics: which acquisition channel produces the best customers
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go


def render(query):
    st.markdown("## Customer Analytics")
    st.markdown("*Campaigns buy customers, not clicks. This module measures whether those customers "
                "come back and what they're worth against what we paid to acquire them.*")
    st.markdown("---")

    orders = query("""
        SELECT o.customer_id, o.order_date, o.revenue, o.order_number,
               c.acquisition_date, c.acquisition_channel, c.segment
        FROM fact_orders o JOIN dim_customers c USING (customer_id)
    """)
    orders["order_date"] = pd.to_datetime(orders["order_date"])
    orders["acquisition_date"] = pd.to_datetime(orders["acquisition_date"])
    orders["cohort_month"] = orders["acquisition_date"].dt.to_period("M").astype(str)
    orders["months_since"] = ((orders["order_date"].dt.year - orders["acquisition_date"].dt.year) * 12
                              + (orders["order_date"].dt.month - orders["acquisition_date"].dt.month)).clip(lower=0)

    # ── Unit economics ────────────────────────────────────────────────────────
    n_cust = orders["customer_id"].nunique()
    total_rev = orders["revenue"].sum()
    clv = total_rev / n_cust
    aov = orders["revenue"].mean()
    orders_per_cust = len(orders) / n_cust
    repeat_rate = (orders.groupby("customer_id")["order_number"].max() > 1).mean()

    # CAC: total ad spend / customers acquired (media-driven CAC proxy)
    spend = query("SELECT SUM(spend) AS s FROM fact_campaign_performance")["s"].iloc[0]
    cac = spend / n_cust
    ltv_cac = clv / cac if cac > 0 else np.nan

    # Payback: cumulative avg revenue per customer by month vs CAC
    cum_rev = (orders.groupby("months_since")["revenue"].sum().cumsum() / n_cust)
    payback_month = next((int(m) for m, v in cum_rev.items() if v >= cac), None)

    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Avg CLV (12-mo)", f"${clv:,.0f}")
    m2.metric("CAC", f"${cac:,.0f}")
    m3.metric("LTV / CAC", f"{ltv_cac:.2f}x")
    m4.metric("Payback Period", f"{payback_month} mo" if payback_month is not None else "> 12 mo")
    m5.metric("AOV", f"${aov:,.0f}")
    m6.metric("Repeat Rate", f"{repeat_rate:.0%}")

    if ltv_cac >= 3:
        st.success(f"LTV/CAC of {ltv_cac:.1f}x is above the 3x healthy benchmark — acquisition spend is value-accretive.")
    elif ltv_cac >= 1:
        st.warning(f"LTV/CAC of {ltv_cac:.1f}x is positive but below the 3x benchmark — margin after service costs may be thin.")
    else:
        st.error(f"LTV/CAC of {ltv_cac:.1f}x — we lose money on each acquired customer at current economics.")

    # ── Cohort retention heatmap ──────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Cohort Retention (% of cohort placing an order in month N)")

    cohort_sizes = orders[orders["order_number"] == 1].groupby("cohort_month")["customer_id"].nunique()
    active = orders.groupby(["cohort_month", "months_since"])["customer_id"].nunique().reset_index()
    active["retention"] = active.apply(
        lambda r: r["customer_id"] / cohort_sizes[r["cohort_month"]] * 100, axis=1)

    heat = active.pivot(index="cohort_month", columns="months_since", values="retention")
    heat = heat.loc[:, [c for c in heat.columns if c <= 11]]

    fig = px.imshow(heat, color_continuous_scale="Teal", aspect="auto",
                    labels=dict(x="Months since acquisition", y="Acquisition cohort", color="Retention %"),
                    template="plotly_dark", height=420, text_auto=".0f")
    fig.update_layout(margin=dict(t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)
    st.caption("Month 0 = 100% by definition (acquisition order). Reading down a column compares cohort quality over time; "
               "reading across a row shows decay for one cohort.")

    # ── Channel economics ─────────────────────────────────────────────────────
    st.markdown("---")
    col1, col2 = st.columns(2)

    ch = orders.groupby("acquisition_channel").agg(
        customers=("customer_id", "nunique"),
        revenue=("revenue", "sum"),
        orders=("revenue", "count"),
    )
    ch["clv"] = ch["revenue"] / ch["customers"]
    ch["repeat_rate"] = orders.groupby(["acquisition_channel", "customer_id"])["order_number"].max().gt(1).groupby("acquisition_channel").mean()

    with col1:
        st.markdown("#### CLV by Acquisition Channel")
        fig2 = px.bar(ch.reset_index().sort_values("clv", ascending=False),
                      x="acquisition_channel", y="clv", color="clv",
                      color_continuous_scale="teal", template="plotly_dark", height=320)
        fig2.update_layout(margin=dict(t=10, b=10), yaxis_title="Avg CLV ($)",
                           xaxis_title="", coloraxis_showscale=False)
        st.plotly_chart(fig2, use_container_width=True)

    with col2:
        st.markdown("#### Retention by Acquisition Channel")
        ch_ret = orders.groupby(["acquisition_channel", "months_since"])["customer_id"].nunique().reset_index()
        ch_sizes = orders[orders["order_number"] == 1].groupby("acquisition_channel")["customer_id"].nunique()
        ch_ret["retention"] = ch_ret.apply(lambda r: r["customer_id"] / ch_sizes[r["acquisition_channel"]] * 100, axis=1)
        ch_ret = ch_ret[ch_ret["months_since"].between(1, 8)]
        fig3 = px.line(ch_ret, x="months_since", y="retention", color="acquisition_channel",
                       template="plotly_dark", height=320, markers=True)
        fig3.update_layout(margin=dict(t=10, b=10), yaxis_title="Retention %",
                           xaxis_title="Months since acquisition")
        st.plotly_chart(fig3, use_container_width=True)

    best = ch["clv"].idxmax()
    worst = ch["clv"].idxmin()
    st.info(f"**Insight:** {best}-acquired customers are worth ${ch.loc[best, 'clv']:,.0f} on average vs "
            f"${ch.loc[worst, 'clv']:,.0f} for {worst} — a {ch.loc[best, 'clv'] / ch.loc[worst, 'clv'] - 1:.0%} gap. "
            f"CAC targets should be set per channel, not as a single blended number.")

    # ── Cumulative CLV / payback curve ───────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Payback Curve — Cumulative Revenue per Customer vs CAC")
    curve = cum_rev.reset_index()
    curve.columns = ["months_since", "cum_revenue"]
    curve = curve[curve["months_since"] <= 11]
    fig4 = go.Figure()
    fig4.add_scatter(x=curve["months_since"], y=curve["cum_revenue"], mode="lines+markers",
                     name="Cumulative revenue / customer", line=dict(color="#06b6d4", width=3))
    fig4.add_hline(y=cac, line_dash="dash", line_color="#f59e0b",
                   annotation_text=f"CAC ${cac:,.0f}")
    fig4.update_layout(template="plotly_dark", height=320, margin=dict(t=10, b=10),
                       xaxis_title="Months since acquisition", yaxis_title="$ per customer")
    st.plotly_chart(fig4, use_container_width=True)
