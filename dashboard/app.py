import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

API_URL = "http://localhost:8000/analytics"

st.set_page_config(
    page_title="Binance P2P Analytics",
    layout="wide"
)

st.title("Binance P2P Analytics Dashboard")

# =========================================================
# SIDEBAR FILTERS
# =========================================================

st.sidebar.header("Filters")

asset = st.sidebar.selectbox(
    "Asset",
    ["USDT"]
)

fiat = st.sidebar.selectbox(
    "Fiat",
    ["EUR", "USD"]
)

trade_type = st.sidebar.selectbox(
    "Trade Type",
    ["BUY", "SELL"]
)

window = st.sidebar.selectbox(
    "Timeframe",
    ["24h", "12h", "1h"]
)

# =========================================================
# API CALLS
# =========================================================

snapshot = requests.get(
    f"{API_URL}/snapshot",
    params={
        "asset": asset,
        "fiat": fiat,
        "tf": window
    }
).json()

spread = requests.get(
    f"{API_URL}/spread",
    params={
        "asset": asset,
        "fiat": fiat,
        "tf": window
    }
).json()

spread_windows = requests.get(
    f"{API_URL}/spread-all-windows",
    params={
        "asset": asset,
        "fiat": fiat
    }
).json()

momentum = requests.get(
    f"{API_URL}/momentum",
    params={
        "asset": asset,
        "fiat": fiat,
        "trade_type": trade_type
    }
).json()

volatility = requests.get(
    f"{API_URL}/volatility",
    params={
        "asset": asset,
        "fiat": fiat,
        "trade_type": trade_type
    }
).json()

liquidity = requests.get(
    f"{API_URL}/liquidity",
    params={
        "asset": asset,
        "fiat": fiat,
        "trade_type": trade_type
    }
).json()

score = requests.get(
    f"{API_URL}/efficiency-score",
    params={
        "asset": asset,
        "fiat": fiat
    }
).json()

leaderboard = requests.get(
    f"{API_URL}/leaderboard"
).json()

cross_window = requests.get(
    f"{API_URL}/cross-window",
    params={
        "asset": asset,
        "fiat": fiat
    }
).json()

# =========================================================
# KPI ROW
# =========================================================

st.subheader("Market KPIs")

col1, col2, col3, col4 = st.columns(4)

col1.metric(
    "Spread %",
    spread.get("spread_pct", 0)
)

col2.metric(
    "Net %",
    spread.get("net_pct", 0)
)

col3.metric(
    "Momentum %",
    momentum.get("momentum_vs_24h_pct", 0)
)

col4.metric(
    "Efficiency Score",
    score.get("score", 0)
)

st.divider()

# =========================================================
# MARKET EFFICIENCY GAUGE
# =========================================================

st.subheader("Market Efficiency Gauge")

fig_gauge = go.Figure(go.Indicator(
    mode="gauge+number",
    value=score.get("score", 0),
    title={"text": "Efficiency Score"},
    gauge={
        "axis": {"range": [0, 100]},
        "bar": {"thickness": 0.3},
        "steps": [
            {"range": [0, 40]},
            {"range": [40, 70]},
            {"range": [70, 100]}
        ]
    }
))

st.plotly_chart(fig_gauge, use_container_width=True)

# =========================================================
# SPREAD TREND CHART
# =========================================================

st.subheader("Spread Trend Across Windows")

if isinstance(spread_windows, list) and len(spread_windows) > 0:

    spread_df = pd.DataFrame(spread_windows)

    fig_spread = px.bar(
        spread_df,
        x="window",
        y="spread_pct",
        text="spread_pct"
    )

    st.plotly_chart(fig_spread, use_container_width=True)

# =========================================================
# MOMENTUM TREND
# =========================================================

st.subheader("Price Momentum")

momentum_df = pd.DataFrame({
    "Window": ["1h", "12h", "24h"],
    "Price": [
        momentum.get("price_1h", 0),
        momentum.get("price_12h", 0),
        momentum.get("price_24h", 0),
    ]
})

fig_momentum = px.line(
    momentum_df,
    x="Window",
    y="Price",
    markers=True
)

st.plotly_chart(fig_momentum, use_container_width=True)

# =========================================================
# VOLATILITY ANALYSIS
# =========================================================

st.subheader("Volatility Analysis")

vol_rows = []

for key in ["1h", "12h", "24h"]:
    if key in volatility:
        vol_rows.append({
            "window": key,
            "volatility_ratio": volatility[key]["volatility_ratio"]
        })

if vol_rows:
    vol_df = pd.DataFrame(vol_rows)

    fig_vol = px.bar(
        vol_df,
        x="window",
        y="volatility_ratio",
        text="volatility_ratio"
    )

    st.plotly_chart(fig_vol, use_container_width=True)

# =========================================================
# LIQUIDITY ANALYSIS
# =========================================================

st.subheader("Liquidity Analysis")

liq_rows = []

for key, val in liquidity.get("windows", {}).items():
    liq_rows.append({
        "window": key,
        "liquidity": val["liquidity"]
    })

if liq_rows:
    liq_df = pd.DataFrame(liq_rows)

    fig_liq = px.bar(
        liq_df,
        x="window",
        y="liquidity",
        text="liquidity"
    )

    st.plotly_chart(fig_liq, use_container_width=True)

# =========================================================
# CROSS WINDOW TABLE
# =========================================================

st.subheader("Cross Window Comparison")

if isinstance(cross_window, list) and len(cross_window) > 0:
    cross_df = pd.DataFrame(cross_window)
    st.dataframe(cross_df)

# =========================================================
# LEADERBOARD
# =========================================================

st.subheader("Market Leaderboard")

if isinstance(leaderboard, list) and len(leaderboard) > 0:

    leaderboard_df = pd.DataFrame(leaderboard)

    st.dataframe(leaderboard_df)

    fig_leader = px.bar(
        leaderboard_df.head(10),
        x="pair",
        y="score",
        text="score"
    )

    st.plotly_chart(fig_leader, use_container_width=True)

elif isinstance(leaderboard, dict):

    st.error("Leaderboard API Error")
    st.json(leaderboard)

else:
    st.info("No leaderboard data available")

# =========================================================
# SNAPSHOT TABLE
# =========================================================

st.subheader("Market Snapshot")

if isinstance(snapshot, dict):

    snapshot_rows = []

    for side, values in snapshot.items():

        # ensure nested dict
        if isinstance(values, dict):

            row = values.copy()
            row["side"] = side
            snapshot_rows.append(row)

    if len(snapshot_rows) > 0:

        snapshot_df = pd.DataFrame(snapshot_rows)
        st.dataframe(snapshot_df)

    else:
        st.warning("Snapshot returned no market rows")
        st.json(snapshot)

else:
    st.error("Invalid snapshot response")
    st.write(snapshot)