"""Experiment Center — A/B test analysis with proper statistical inference.

Methodology:
- Two-proportion z-test for the primary metric (CTR / conversion rate)
- 95% confidence interval on absolute and relative lift
- Post-hoc power analysis and required-sample-size calculator
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from scipy import stats


def two_proportion_ztest(x1, n1, x2, n2):
    """Returns z, p-value (two-sided), pooled SE."""
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se = np.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    z = (p2 - p1) / se if se > 0 else 0.0
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))
    return z, p_value, se


def lift_confidence_interval(x1, n1, x2, n2, alpha=0.05):
    """95% CI on the absolute difference in proportions (unpooled SE)."""
    p1, p2 = x1 / n1, x2 / n2
    se = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    zcrit = stats.norm.ppf(1 - alpha / 2)
    diff = p2 - p1
    return diff - zcrit * se, diff + zcrit * se


def achieved_power(p1, p2, n_per_group, alpha=0.05):
    """Post-hoc power of a two-proportion z-test."""
    if p1 == p2:
        return alpha
    p_bar = (p1 + p2) / 2
    se0 = np.sqrt(2 * p_bar * (1 - p_bar) / n_per_group)
    se1 = np.sqrt(p1 * (1 - p1) / n_per_group + p2 * (1 - p2) / n_per_group)
    zcrit = stats.norm.ppf(1 - alpha / 2)
    z_beta = (abs(p2 - p1) - zcrit * se0) / se1
    return float(stats.norm.cdf(z_beta))


def required_sample_size(p1, mde_rel, alpha=0.05, power=0.80):
    """Users per variant to detect a relative lift `mde_rel` on baseline p1."""
    p2 = p1 * (1 + mde_rel)
    z_a = stats.norm.ppf(1 - alpha / 2)
    z_b = stats.norm.ppf(power)
    p_bar = (p1 + p2) / 2
    n = ((z_a * np.sqrt(2 * p_bar * (1 - p_bar)) + z_b * np.sqrt(p1 * (1 - p1) + p2 * (1 - p2))) ** 2) / ((p2 - p1) ** 2)
    return int(np.ceil(n))


def render(query):
    st.markdown("## Experiment Center")
    st.markdown("*A/B test readouts with statistical rigor — significance, confidence intervals, and power. "
                "No experiment ships a decision without passing this review.*")
    st.markdown("---")

    exps = query("SELECT DISTINCT experiment_id, experiment_name, channel, primary_metric FROM fact_experiments ORDER BY experiment_id")
    exp_label = st.selectbox(
        "Select experiment:",
        exps["experiment_id"] + " — " + exps["experiment_name"]
    )
    exp_id = exp_label.split(" — ")[0]
    exp_meta = exps[exps["experiment_id"] == exp_id].iloc[0]

    df = query(f"""
        SELECT variant, date, SUM(users) AS users, SUM(successes) AS successes, SUM(revenue) AS revenue
        FROM fact_experiments WHERE experiment_id = '{exp_id}'
        GROUP BY variant, date ORDER BY date
    """)
    agg = df.groupby("variant")[["users", "successes", "revenue"]].sum()

    x_c, n_c = int(agg.loc["Control", "successes"]),   int(agg.loc["Control", "users"])
    x_t, n_t = int(agg.loc["Treatment", "successes"]), int(agg.loc["Treatment", "users"])
    p_c, p_t = x_c / n_c, x_t / n_t

    z, p_value, _ = two_proportion_ztest(x_c, n_c, x_t, n_t)
    ci_low, ci_high = lift_confidence_interval(x_c, n_c, x_t, n_t)
    rel_lift = (p_t - p_c) / p_c * 100
    power = achieved_power(p_c, p_t, min(n_c, n_t))
    significant = p_value < 0.05

    # ── Verdict banner ────────────────────────────────────────────────────────
    if significant and rel_lift > 0:
        st.success(f"**Winner: Treatment** — {rel_lift:+.1f}% relative lift in {exp_meta['primary_metric']} "
                   f"(p = {p_value:.4f}). Result is statistically significant at α = 0.05. Recommend rollout.")
    elif significant and rel_lift < 0:
        st.error(f"**Winner: Control** — Treatment underperformed by {abs(rel_lift):.1f}% "
                 f"(p = {p_value:.4f}). Statistically significant. Do not ship Treatment.")
    else:
        st.warning(f"**Inconclusive** — {rel_lift:+.1f}% observed lift, but p = {p_value:.4f} (> 0.05). "
                   f"Achieved power: {power:.0%}. Do not ship; extend the test or accept the null.")

    # ── Headline metrics ──────────────────────────────────────────────────────
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric(f"Control {exp_meta['primary_metric']}",   f"{p_c:.3%}")
    m2.metric(f"Treatment {exp_meta['primary_metric']}", f"{p_t:.3%}", f"{rel_lift:+.1f}%")
    m3.metric("p-value", f"{p_value:.4f}")
    m4.metric("z-statistic", f"{z:.2f}")
    m5.metric("Statistical Power", f"{power:.0%}")
    m6.metric("Sample Size", f"{n_c + n_t:,}")

    st.caption(f"95% CI on absolute lift: [{ci_low:+.4f}, {ci_high:+.4f}] "
               f"({'excludes' if significant else 'includes'} zero → "
               f"{'significant' if significant else 'not significant'})")

    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Daily Rate by Variant")
        daily = df.copy()
        daily["rate"] = daily["successes"] / daily["users"]
        fig = go.Figure()
        for variant, color in [("Control", "#94a3b8"), ("Treatment", "#06b6d4")]:
            d = daily[daily["variant"] == variant]
            fig.add_scatter(x=d["date"], y=d["rate"], name=variant, mode="lines",
                            line=dict(color=color, width=2))
        fig.update_layout(template="plotly_dark", height=300, margin=dict(t=10, b=10),
                          yaxis_tickformat=".2%")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("#### Estimated Lift with 95% CI")
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=[(p_t - p_c)], y=["Treatment vs Control"], mode="markers",
            marker=dict(size=14, color="#06b6d4"),
            error_x=dict(type="data", symmetric=False,
                         array=[ci_high - (p_t - p_c)], arrayminus=[(p_t - p_c) - ci_low],
                         color="#f59e0b", thickness=3, width=10),
        ))
        fig2.add_vline(x=0, line_dash="dash", line_color="#ef4444",
                       annotation_text="No effect")
        fig2.update_layout(template="plotly_dark", height=300, margin=dict(t=10, b=10),
                           xaxis_title="Absolute lift in rate", xaxis_tickformat=".3%")
        st.plotly_chart(fig2, use_container_width=True)

    # ── All experiments summary ───────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Experiment Portfolio")
    all_exp = query("""
        SELECT experiment_id, experiment_name, primary_metric, variant,
               SUM(users) AS users, SUM(successes) AS successes
        FROM fact_experiments GROUP BY 1,2,3,4
    """)
    rows = []
    for eid in all_exp["experiment_id"].unique():
        sub = all_exp[all_exp["experiment_id"] == eid].set_index("variant")
        xc, nc = int(sub.loc["Control", "successes"]), int(sub.loc["Control", "users"])
        xt, nt = int(sub.loc["Treatment", "successes"]), int(sub.loc["Treatment", "users"])
        _, pv, _ = two_proportion_ztest(xc, nc, xt, nt)
        lift = (xt / nt - xc / nc) / (xc / nc) * 100
        verdict = ("✓ Ship Treatment" if pv < 0.05 and lift > 0
                   else "✗ Keep Control" if pv < 0.05
                   else "— Inconclusive")
        rows.append({
            "Experiment": sub.loc["Control", "experiment_name"],
            "Metric": sub.loc["Control", "primary_metric"],
            "Lift": f"{lift:+.1f}%", "p-value": f"{pv:.4f}",
            "Sample": f"{nc + nt:,}", "Decision": verdict,
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Sample size calculator ────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Sample Size Calculator (Pre-test Planning)")
    c1, c2, c3, c4 = st.columns(4)
    base = c1.number_input("Baseline rate (%)", 0.5, 50.0, 4.0, 0.5) / 100
    mde = c2.number_input("Min detectable lift (%)", 1.0, 50.0, 10.0, 1.0) / 100
    alpha = c3.selectbox("Significance (α)", [0.05, 0.01, 0.10])
    target_power = c4.selectbox("Power (1-β)", [0.80, 0.90, 0.95])
    n_req = required_sample_size(base, mde, alpha, target_power)
    st.info(f"**{n_req:,} users per variant** ({2 * n_req:,} total) needed to detect a "
            f"{mde:.0%} relative lift on a {base:.1%} baseline at α = {alpha}, power = {target_power:.0%}.")
