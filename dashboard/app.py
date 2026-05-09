import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from supabase import create_client, Client
from dotenv import load_dotenv
import os

# --- 1. CONFIG & AUTH ---
st.set_page_config(page_title="P2P Sentinel", layout="wide", page_icon="🛡️")

def get_supabase_client() -> Client:
    load_dotenv()
    url = os.environ.get("SUPABASE_URL") or st.secrets.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY") or st.secrets.get("SUPABASE_KEY")
    
    if not url or not key:
        st.error("Credentials missing. Check .env or Streamlit Secrets.")
        st.stop()
    return create_client(url, key)

supabase = get_supabase_client()

# --- 2. SIDEBAR FILTERS ---
st.sidebar.title("🛡️ P2P Sentinel")
selected_asset = st.sidebar.selectbox("Select Asset", ["USDT"])
selected_fiat = st.sidebar.selectbox("Select Fiat", ["EUR", "USD"])

# --- 3. DATA LOADING (Updated with parameters to fix caching) ---
@st.cache_data(ttl=30)
def load_data(fiat_code, asset_code):
    try:
        # Fetch raw market data
        raw_res = supabase.table("p2p_market_data") \
            .select("*") \
            .eq("fiat", fiat_code) \
            .eq("asset", asset_code) \
            .order("created_at", desc=True) \
            .limit(100) \
            .execute()
        
        # Fetch latest processed insight
        insight_res = supabase.table("p2p_insights") \
            .select("*") \
            .eq("fiat", fiat_code) \
            .eq("asset", asset_code) \
            .order("processed_at", desc=True) \
            .limit(1) \
            .execute()
        
        df_raw = pd.DataFrame(raw_res.data)
        insight_data = insight_res.data[0] if insight_res.data else None
        
        return df_raw, insight_data
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame(), None

# Load data based on sidebar selection
df, latest_insight = load_data(selected_fiat, selected_asset)

# --- 4. DASHBOARD UI ---

if latest_insight:
    # -- TOP ROW: Metrics --
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Market Spread", f"{latest_insight.get('market_spread_pct', 0)}%")
    m2.metric("Trust Score (Avg)", f"{latest_insight.get('market_trust_avg', 0)}/100")
    m3.metric("Triangle Profit", f"{latest_insight.get('fx_rate_gap_pct', 0)}%")
    m4.metric("Whale Ads (>10k)", latest_insight.get('whale_count', 0))

    # -- MIDDLE ROW: Visuals --
    st.divider()
    c1, c2 = st.columns([1, 1])

    with c1:
        st.subheader("⚖️ Spread Gauge")
        val = latest_insight.get('market_spread_pct', 0)
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = val,
            gauge = {
                'axis': {'range': [0, 2]}, 
                'bar': {'color': "#00CC96" if val < 0.5 else "#EF553B"},
                'steps': [
                    {'range': [0, 0.5], 'color': "rgba(0, 204, 150, 0.2)"},
                    {'range': [0.5, 2], 'color': "rgba(239, 85, 59, 0.1)"}
                ]
            }
        ))
        fig_gauge.update_layout(height=300, margin=dict(l=20, r=20, t=40, b=20))
        st.plotly_chart(fig_gauge, use_container_width=True)

    with c2:
        st.subheader("🎯 Safety Scatter Plot")
        if not df.empty:
            fig_scatter = px.scatter(
                df, x="price", y="trust_score", 
                size="surplus_amount", color="is_pro",
                hover_data=["merchant_name", "finish_rate", "payment_methods"],
                title="Price vs. Reliability",
                color_discrete_map={True: "#00CC96", False: "#636EFA"}
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

    # -- BOTTOM ROW: Depth --
    st.subheader("🌊 Order Book Depth (Sell Side)")
    depth_data = latest_insight.get('order_book_depth', {})
    if depth_data:
        # Sort and clean labels like '(10.1, 10.2]'
        depth_df = pd.DataFrame(list(depth_data.items()), columns=['Price Range', 'Volume'])
        fig_depth = px.bar(depth_df, x='Price Range', y='Volume', 
                           color='Volume', color_continuous_scale="Viridis",
                           template="plotly_dark")
        st.plotly_chart(fig_depth, use_container_width=True)

    # -- ADVERTISER SECTION --
    st.divider()
    st.subheader("👤 Advertiser Intelligence")
    col1, col2, col3 = st.columns(3)

    with col1:
        v_ratio = latest_insight.get('verified_ratio', 0)
        st.metric("Verified Merchant %", f"{round(v_ratio * 100, 1)}%")
        st.caption("Percentage of Pro Merchants in the current batch")

    with col2:
        st.metric("Risky Ads", latest_insight.get('risky_ads', 0), delta="-Warning", delta_color="inverse")
        st.caption("Ads from merchants with <85% completion rate")

    with col3:
        st.info(f"**Dominant Merchant:** {latest_insight.get('top_merchant', 'N/A')}")
        st.caption("Most frequent advertiser in this market")

    # -- RELIABILITY TABLE --
    st.write("### 🏆 Top 5 Reliable Offers")
    if not df.empty:
        # Filter: Best Price + High Trust + Pro
        reliable = df[(df['trust_score'] > 90) & (df['trade_type'] == 'BUY')].sort_values("price").head(5)
        if not reliable.empty:
            st.dataframe(
                reliable[['merchant_name', 'price', 'finish_rate', 'month_orders', 'is_pro', 'payment_methods']],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.write("No high-trust ads found at the moment.")

else:
    st.warning(f"No insight data found for {selected_asset}/{selected_fiat}. Run the processor.py script to generate stats.")