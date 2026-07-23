"""Attribution Modeling — how much credit does each channel deserve?

Implements five rule-based multi-touch attribution models over customer
journeys (fact_touchpoints):
- First Touch:    100% credit to the first touchpoint
- Last Touch:     100% credit to the final (converting) touchpoint
- Linear:         equal credit to every touchpoint
- Time Decay:     exponentially more credit to touches closer to conversion
- Position-Based: 40% first, 40% last, 20% split across the middle (U-shaped)
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

DECAY_HALF_LIFE = 7.0  # days


def compute_attribution(tp: pd.DataFrame, first_rev: pd.DataFrame) -> pd.DataFrame:
    """Returns channel-level attributed revenue under each model."""
    df = tp.merge(first_rev, on="customer_id", how="inner")
    df["touch_date"] = pd.to_datetime(df["touch_date"])

    conv_date = df.groupby("customer_id")["touch_date"].transform("max")
    days_before = (conv_date - df["touch_date"]).dt.days.clip(lower=0)

    n = df["total_touches"]
    is_first = df["touch_number"] == 1
    is_last = df["touch_number"] == n

    # Model weights (per touchpoint, sum to 1 within each journey)
    df["w_first"] = np.where(is_first, 1.0, 0.0)
    df["w_last"] = np.where(is_last, 1.0, 0.0)
    df["w_linear"] = 1.0 / n

    df["_decay_raw"] = 0.5 ** (days_before / DECAY_HALF_LIFE)
    df["w_decay"] = df["_decay_raw"] / df.groupby("customer_id")["_decay_raw"].transform("sum")

    middle = (~is_first) & (~is_last)
    n_middle = (n - 2).clip(lower=1)
    df["w_position"] = np.select(
        [n == 1, n == 2, is_first, is_last],
        [1.0, 0.5, 0.4, 0.4],
        default=0.0
    )
    df.loc[middle & (n > 2), "w_position"] = 0.2 / n_middle[middle & (n > 2)]

    out = []
    for model, col in [("First Touch", "w_first"), ("Last Touch", "w_last"),
                       ("Linear", "w_linear"), ("Time Decay", "w_decay"),
                       ("Position-Based", "w_position")]:
        credited = (df[col] * df["revenue"]).groupby(df["channel"]).sum()
        for ch, val in credited.items():
            out.append({"model": model, "channel": ch, "attributed_revenue": val})
    return pd.DataFrame(out)


def render(query):
    st.markdown("## Attribution Modeling")
    st.markdown("*The same conversions, five different stories. Attribution decides which channels get "
                "budget — so we compare models instead of trusting one.*")
    st.markdown("---")

    tp = query("SELECT customer_id, touch_number, total_touches, channel, touch_date FROM fact_touchpoints")
    first_rev = query("""
        SELECT customer_id, revenue FROM fact_orders WHERE order_number = 1
    """)

    attr = compute_attribution(tp, first_rev)

    # ── Headline stats ────────────────────────────────────────────────────────
    journeys = tp.groupby("customer_id")["total_touches"].first()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Converting Journeys", f"{len(journeys):,}")
    m2.metric("Total Touchpoints", f"{len(tp):,}")
    m3.metric("Avg Touches / Journey", f"{journeys.mean():.1f}")
    m4.metric("Multi-Touch Journeys", f"{(journeys > 1).mean():.0%}")

    st.markdown("---")
    col1, col2 = st.columns([3, 2])

    with col1:
        st.markdown("#### Attributed Revenue by Model")
        fig = px.bar(attr, x="channel", y="attributed_revenue", color="model",
                     barmode="group", template="plotly_dark", height=380,
                     color_discrete_sequence=["#64748b", "#06b6d4", "#22d3ee", "#f59e0b", "#a78bfa"])
        fig.update_layout(margin=dict(t=10, b=10), yaxis_title="Attributed Revenue ($)")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("#### Model Disagreement")
        pivot = attr.pivot(index="channel", columns="model", values="attributed_revenue")
        pivot["Spread"] = pivot.max(axis=1) - pivot.min(axis=1)
        pivot = pivot.sort_values("Spread", ascending=False)
        disagreement = pivot[["Spread"]].reset_index()
        fig2 = px.bar(disagreement, x="Spread", y="channel", orientation="h",
                      template="plotly_dark", height=380, color="Spread",
                      color_continuous_scale="Oranges")
        fig2.update_layout(margin=dict(t=10, b=10), xaxis_title="Max − Min attributed revenue ($)",
                           coloraxis_showscale=False)
        st.plotly_chart(fig2, use_container_width=True)

    biggest = pivot.index[0]
    lt = pivot.loc[biggest, "Last Touch"]
    ft = pivot.loc[biggest, "First Touch"]
    direction = "over" if lt > ft else "under"
    st.info(f"**Insight:** Model choice matters most for **{biggest}** — last-touch {direction}-credits it by "
            f"${abs(lt - ft):,.0f} vs first-touch. Channels that open journeys (upper-funnel) lose credit "
            f"under last-touch; channels that close them gain it.")

    # ── Journey explorer ──────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Journey Explorer")
    st.caption("A sample multi-touch journey and how each model splits the credit.")

    multi = tp[tp["total_touches"].between(3, 5)]
    sample_ids = multi["customer_id"].unique()[:50]
    sel_cust = st.selectbox("Customer journey:", sample_ids)

    j = tp[tp["customer_id"] == sel_cust].sort_values("touch_number")
    rev = first_rev[first_rev["customer_id"] == sel_cust]["revenue"].iloc[0]

    path = "  →  ".join(j["channel"].tolist()) + "  →  💰 Purchase"
    st.markdown(f"**Path:** {path} &nbsp;&nbsp;|&nbsp;&nbsp; **Order value:** ${rev:,.2f}")

    single_attr = compute_attribution(j, first_rev[first_rev["customer_id"] == sel_cust])
    fig3 = px.bar(single_attr, x="model", y="attributed_revenue", color="channel",
                  template="plotly_dark", height=300,
                  color_discrete_sequence=px.colors.qualitative.Set2)
    fig3.update_layout(margin=dict(t=10, b=10), yaxis_title="Credit ($)", barmode="stack")
    st.plotly_chart(fig3, use_container_width=True)

    # ── Methodology ───────────────────────────────────────────────────────────
    with st.expander("Methodology notes"):
        st.markdown(f"""
- **First / Last Touch** — 100% of order revenue to the first or final touchpoint.
- **Linear** — revenue split equally across all touches in the journey.
- **Time Decay** — weight `0.5^(days_before_conversion / {DECAY_HALF_LIFE:.0f})`, normalized per journey. Touches closer to conversion earn more.
- **Position-Based (U-shaped)** — 40% first touch, 40% last touch, 20% split across middle touches.
- Rule-based models shown here are industry standard; data-driven attribution (Shapley / Markov) is the natural next step and would use the same journey table.
        """)
