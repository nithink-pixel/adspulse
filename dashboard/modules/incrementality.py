"""Incrementality Analysis — did advertising actually CAUSE revenue?

Geo-holdout experiment: 30 test geos received advertising, 10 holdout geos did
not. Causal effect estimated via difference-in-differences (DiD):

    lift = (Test_post − Test_pre) − (Holdout_post − Holdout_pre)

The holdout's pre→post change removes seasonality and organic trend, isolating
the incremental effect of ads. A t-test on geo-level lift confirms significance.
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from scipy import stats


def render(query):
    st.markdown("## Incrementality Analysis")
    st.markdown("*ROAS tells you revenue that came WITH ads. Incrementality tells you revenue that came "
                "BECAUSE OF ads. Geo-holdout testing separates the two.*")
    st.markdown("---")

    geo = query("SELECT * FROM fact_geo_experiment")

    # ── Difference-in-differences ─────────────────────────────────────────────
    weekly_avg = geo.groupby(["geo_group", "period", "geo_id"])["revenue"].mean().reset_index()
    means = weekly_avg.groupby(["geo_group", "period"])["revenue"].mean().unstack()

    test_pre, test_post = means.loc["Test (ads on)", "Pre"], means.loc["Test (ads on)", "Test"]
    hold_pre, hold_post = means.loc["Holdout (no ads)", "Pre"], means.loc["Holdout (no ads)", "Test"]

    counterfactual = test_pre * (hold_post / hold_pre)   # what test geos would have done without ads
    lift_per_geo_week = test_post - counterfactual
    lift_pct = lift_per_geo_week / counterfactual * 100

    n_test_geos = geo[geo["geo_group"] == "Test (ads on)"]["geo_id"].nunique()
    test_weeks = geo[geo["period"] == "Test"]["week"].nunique()
    total_incremental = lift_per_geo_week * n_test_geos * test_weeks
    total_spend = geo["ad_spend"].sum()
    iroas = total_incremental / total_spend if total_spend > 0 else np.nan

    observed_test_rev = geo[(geo["geo_group"] == "Test (ads on)") & (geo["period"] == "Test")]["revenue"].sum()
    baseline_rev = counterfactual * n_test_geos * test_weeks

    # Significance: t-test on geo-level DiD estimates
    per_geo = weekly_avg.pivot_table(index=["geo_id", "geo_group"], columns="period", values="revenue").reset_index()
    per_geo["scaled_lift"] = per_geo["Test"] - per_geo["Pre"] * (hold_post / hold_pre)
    test_lifts = per_geo[per_geo["geo_group"] == "Test (ads on)"]["scaled_lift"]
    hold_lifts = per_geo[per_geo["geo_group"] == "Holdout (no ads)"]["scaled_lift"]
    t_stat, p_val = stats.ttest_ind(test_lifts, hold_lifts, equal_var=False)

    # ── Headline ──────────────────────────────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Observed Revenue (test geos)", f"${observed_test_rev / 1e6:.1f}M")
    m2.metric("Modeled Baseline (no ads)", f"${baseline_rev / 1e6:.1f}M")
    m3.metric("Incremental Revenue", f"${total_incremental / 1e6:.2f}M", f"{lift_pct:+.1f}%")
    m4.metric("Incremental ROAS", f"{iroas:.2f}x")
    m5.metric("p-value (geo t-test)", f"{p_val:.4f}")

    if p_val < 0.05:
        st.success(f"**Advertising is causally driving revenue.** Test geos outperformed their no-ads counterfactual "
                   f"by {lift_pct:.1f}% (t = {t_stat:.2f}, p = {p_val:.4f}). Every ad dollar returned "
                   f"${iroas:.2f} of *incremental* revenue — revenue that would not have occurred otherwise.")
    else:
        st.warning(f"**Lift not statistically significant** (p = {p_val:.4f}). Observed revenue in test geos may be "
                   f"organic. Do not credit ads with this revenue; consider a longer test or more geos.")

    # ── Charts ────────────────────────────────────────────────────────────────
    st.markdown("---")
    col1, col2 = st.columns(2)

    weekly = geo.groupby(["week", "geo_group"])["revenue"].mean().reset_index()

    with col1:
        st.markdown("#### Weekly Revenue per Geo — Test vs Holdout")
        fig = go.Figure()
        for grp, color in [("Test (ads on)", "#06b6d4"), ("Holdout (no ads)", "#94a3b8")]:
            d = weekly[weekly["geo_group"] == grp]
            fig.add_scatter(x=d["week"], y=d["revenue"], name=grp, mode="lines+markers",
                            line=dict(color=color, width=2))
        fig.add_vline(x=7.5, line_dash="dash", line_color="#f59e0b",
                      annotation_text="Ads launch")
        fig.update_layout(template="plotly_dark", height=340, margin=dict(t=10, b=10),
                          xaxis_title="Week", yaxis_title="Avg revenue per geo ($)")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("#### Observed vs Counterfactual (Test Geos)")
        fig2 = go.Figure()
        fig2.add_bar(x=["Baseline<br>(counterfactual)", "Observed<br>(with ads)"],
                     y=[baseline_rev, observed_test_rev],
                     marker_color=["#475569", "#06b6d4"],
                     text=[f"${baseline_rev/1e6:.1f}M", f"${observed_test_rev/1e6:.1f}M"],
                     textposition="outside")
        fig2.add_annotation(x=1, y=observed_test_rev,
                            text=f"+${total_incremental/1e6:.2f}M incremental",
                            showarrow=True, arrowhead=2, ay=-40, font=dict(color="#f59e0b"))
        fig2.update_layout(template="plotly_dark", height=340, margin=dict(t=40, b=10),
                           yaxis_title="Test-period revenue ($)", showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)

    # ── Distribution of geo-level lift ────────────────────────────────────────
    st.markdown("#### Geo-Level Lift Distribution")
    st.caption("Each point = one geo's deviation from its scaled pre-period baseline. "
               "Separation between groups is the causal signal.")
    fig3 = px.strip(per_geo, x="scaled_lift", y="geo_group", color="geo_group",
                    template="plotly_dark", height=260,
                    color_discrete_map={"Test (ads on)": "#06b6d4", "Holdout (no ads)": "#94a3b8"})
    fig3.add_vline(x=0, line_dash="dash", line_color="#ef4444")
    fig3.update_layout(margin=dict(t=10, b=10), showlegend=False,
                       xaxis_title="Weekly revenue lift vs baseline ($)", yaxis_title="")
    st.plotly_chart(fig3, use_container_width=True)

    with st.expander("Why last-click ROAS overstates impact"):
        naive_roas = observed_test_rev / total_spend if total_spend else 0
        st.markdown(f"""
A naive read would credit ads with all test-period revenue: **{naive_roas:.1f}x ROAS**.
The geo experiment shows only **${total_incremental/1e6:.2f}M of ${observed_test_rev/1e6:.1f}M** was
actually caused by ads — true incremental ROAS is **{iroas:.2f}x**, {(1 - iroas/naive_roas):.0%} lower.
Budget decisions made on naive ROAS systematically over-invest in channels that harvest
demand that would have converted anyway (e.g., branded search).
        """)
