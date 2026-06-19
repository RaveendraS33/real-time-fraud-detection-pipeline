"""Streamlit fraud-operations dashboard backed by PostgreSQL."""

import os

import pandas as pd
import plotly.express as px
import psycopg
import streamlit as st
from psycopg.rows import dict_row

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://fraud_app:fraud_dev_password@localhost:5432/fraud_detection",
)
DECISION_COLORS = {
    "approve": "#287D5A",
    "review": "#D49A32",
    "decline": "#C84B4B",
}

st.set_page_config(page_title="Fraud Operations", layout="wide")
st.title("Fraud Operations")
st.caption("Live transaction decisions and investigation queue")


@st.cache_data(ttl=5)
def load_decisions(limit: int = 2_000) -> pd.DataFrame:
    query = """
        SELECT transaction_id, customer_id, event_time, amount, currency,
               risk_score, fraud_probability, decision, triggered_rules,
               detector_version, processed_at, simulation_is_fraud
        FROM fraud_decisions
        ORDER BY event_time DESC
        LIMIT %s
    """
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
        rows = connection.execute(query, (limit,)).fetchall()
    return pd.DataFrame(rows)


@st.fragment(run_every="5s")
def render_dashboard() -> None:
    try:
        decisions = load_decisions()
    except psycopg.Error as exc:
        st.error(f"Decision store is unavailable: {exc.__class__.__name__}")
        return

    if decisions.empty:
        st.info("Waiting for scored transactions")
        return

    alerts = decisions[decisions["decision"] != "approve"]
    alert_rate = len(alerts) / len(decisions) * 100
    labeled = decisions[decisions["simulation_is_fraud"].notna()]
    detected_true_fraud = labeled[
        labeled["simulation_is_fraud"] & (labeled["decision"] != "approve")
    ]
    true_fraud = labeled[labeled["simulation_is_fraud"]]
    recall = len(detected_true_fraud) / len(true_fraud) * 100 if len(true_fraud) else 0

    metric_columns = st.columns(4)
    metric_columns[0].metric("Transactions", f"{len(decisions):,}")
    metric_columns[1].metric("Alert rate", f"{alert_rate:.1f}%")
    metric_columns[2].metric("Declined", f"{(decisions['decision'] == 'decline').sum():,}")
    metric_columns[3].metric("Simulated recall", f"{recall:.1f}%")

    chart_columns = st.columns((1, 2))
    decision_counts = decisions["decision"].value_counts().rename_axis("decision").reset_index(
        name="transactions"
    )
    mix_chart = px.bar(
        decision_counts,
        x="decision",
        y="transactions",
        color="decision",
        color_discrete_map=DECISION_COLORS,
        title="Decision mix",
    )
    mix_chart.update_layout(showlegend=False, margin=dict(l=20, r=20, t=50, b=20))
    chart_columns[0].plotly_chart(mix_chart, use_container_width=True)

    timeline = decisions.copy()
    timeline["minute"] = pd.to_datetime(timeline["event_time"], utc=True).dt.floor("min")
    timeline = timeline.groupby(["minute", "decision"]).size().reset_index(name="transactions")
    volume_chart = px.line(
        timeline,
        x="minute",
        y="transactions",
        color="decision",
        color_discrete_map=DECISION_COLORS,
        markers=True,
        title="Transaction volume",
    )
    volume_chart.update_layout(margin=dict(l=20, r=20, t=50, b=20))
    chart_columns[1].plotly_chart(volume_chart, use_container_width=True)

    st.subheader("Investigation queue")
    if alerts.empty:
        st.info("No transactions currently require investigation")
        return

    queue = alerts[
        [
            "event_time",
            "transaction_id",
            "customer_id",
            "amount",
            "currency",
            "risk_score",
            "decision",
            "triggered_rules",
        ]
    ].copy()
    queue["triggered_rules"] = queue["triggered_rules"].apply(lambda rules: ", ".join(rules))
    st.dataframe(
        queue,
        use_container_width=True,
        hide_index=True,
        column_config={
            "event_time": st.column_config.DatetimeColumn(
                "Event time", format="YYYY-MM-DD HH:mm:ss"
            ),
            "amount": st.column_config.NumberColumn("Amount", format="%.2f"),
            "risk_score": st.column_config.ProgressColumn("Risk", min_value=0, max_value=100),
        },
    )


render_dashboard()
