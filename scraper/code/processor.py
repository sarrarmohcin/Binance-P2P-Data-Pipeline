import os
import time
import logging
import requests
import pandas as pd
from dotenv import load_dotenv
import numpy as np
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("P2PSentinel.Processor")


class P2PProcessor:
    

    def __init__(self, supabase_client):
        self.supabase = supabase_client
        load_dotenv()
        # Ensure your .env has EXCHANGERAT_KEY
        self.fx_api_key = os.getenv("EXCHANGERAT_KEY")
    
    
    
    def analyze_advertisers(self, df):
        """
        Extracts key advertiser metrics to identify 'Safe' vs 'Risky' players.
        """
        if df.empty:
            return {}

        # 1. Top Tier Merchants (Pro/Verified + High Completion)
        top_merchants = df[
            (df['is_pro'] == True) & 
            (df['finish_rate'] > 0.98) & 
            (df['month_orders'] > 500)
        ]

        # 2. Risk Flags: High Price but Low Completion
        suspicious_ads = df[
            (df['finish_rate'] < 0.80) & 
            (df['month_orders'] < 50)
        ]

        return {
            "verified_merchant_ratio": round(len(df[df['is_pro'] == True]) / len(df), 2),
            "avg_merchant_orders": float(df['month_orders'].mean()),
            "top_tier_count": len(top_merchants),
            "risky_advertiser_count": len(suspicious_ads),
            "dominant_advertiser": df['merchant_name'].mode()[0] if not df['merchant_name'].empty else "N/A"
        }
        
    # --- External Data Fetchers ---

    def get_real_fx_rate(self, base="EUR", target="USD"):
        """Fetch live interbank rate from ExchangeRate-API."""
        url = f"https://v6.exchangerate-api.com/v6/{self.fx_api_key}/pair/{base}/{target}"
        try:
            response = requests.get(url, timeout=10).json()
            if response.get('result') == 'success':
                return float(response.get('conversion_rate'))
            return 1.0
        except Exception as e:
            logger.error(f"FX API Error: {e}")
            return 1.0

    def get_binance_spot_price(self, symbol):
        # Binance usually uses EURUSDT, not USDTEUR
        # We can try both or force the standard
        standard_symbol = symbol.replace("USDTEUR", "EURUSDT")
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={standard_symbol}"
        try:
            res = requests.get(url, timeout=10).json()
            if 'price' in res:
                return float(res['price'])
            logger.error(f"Binance API returned: {res}")
            return None
        except Exception as e:
            logger.error(f"Binance Spot Error: {e}")
            return None

    # --- Database Retrieval ---

    def get_latest_p2p_data(self, asset="USDT", fiat="EUR", limit=100):
        """Fetch fresh data from raw p2p_market_data table."""
        try:
            response = self.supabase.table("p2p_market_data") \
                .select("*") \
                .eq("asset", asset) \
                .eq("fiat", fiat) \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            return pd.DataFrame(response.data)
        except Exception as e:
            logger.error(f"Supabase Fetch Error: {e}")
            return pd.DataFrame()

    # --- Logic & Math ---

    def calculate_triangle_profit(self, eur_p2p_price, usd_p2p_price, fx_rate):
        """
        Calculates profit from EUR -> USDT -> USD -> EUR.
        Profit = (Implied Rate / Official Rate) - 1
        """
        if eur_p2p_price <= 0 or fx_rate <= 0:
            return 0.0
        implied_rate = usd_p2p_price / eur_p2p_price
        profit_pct = ((implied_rate / fx_rate) - 1) * 100
        return round(float(profit_pct), 3)

    def process_market_insights(self, asset="USDT", fiat="EUR"):
        """Main engine to calculate and store insights for a specific market pair."""
        df = self.get_latest_p2p_data(asset, fiat)
        if df.empty:
            logger.warning(f"No data found for {asset}/{fiat}. Skipping...")
            return None
        
        # --- New: Advertiser Analysis ---
        adv_insights = self.analyze_advertisers(df)

        # 1. Market Segmentation
        buys = df[df['trade_type'] == 'BUY']  # Ads of people selling to you
        sells = df[df['trade_type'] == 'SELL'] # Ads of people buying from you

        if buys.empty or sells.empty:
            return None

        best_buy = buys['price'].min()
        best_sell = sells['price'].max()
        
        # 2. External Benchmarks
        spot_price = self.get_binance_spot_price(f"{asset}{fiat}")
        bank_fx_rate = self.get_real_fx_rate(base=fiat, target="USD") # Standardizing to USD for comparison

        # 3. Liquidity & Whale Activity
        total_liq = float(df['surplus_amount'].sum())
        whale_count = int(len(df[df['surplus_amount'] > 10000]))

        # 4. Order Book Depth
        depth = buys.groupby(pd.cut(buys["price"], bins=5), observed=False)["surplus_amount"].sum().to_dict()
        depth_json = {str(k): float(v) for k, v in depth.items()}

        # 5. Profit & Spread Metrics
        spread_pct = ((best_buy - best_sell) / best_buy) * 100
        p2p_vs_spot_profit = ((best_buy - spot_price) / spot_price) * 100 if spot_price else 0.0
        
        # Risk Analysis
        avg_finish = df['finish_rate'].mean()
        risk = "Low" if avg_finish > 0.95 else "Medium" if avg_finish > 0.85 else "High"

        # 6. Triangle Arbitrage Calculation
        # We need the other side (USD) to compare. For this logic, we fetch the best USD price.
        usd_df = self.get_latest_p2p_data(asset, "USD", limit=5)
        best_usd_p2p = usd_df[usd_df['trade_type'] == 'BUY']['price'].min() if not usd_df.empty else 0.0
        
        triangle_profit = self.calculate_triangle_profit(best_buy, best_usd_p2p, bank_fx_rate)

        def clean_val(val):
            """Convert NaN/Inf to 0.0 for JSON compatibility."""
            if val is None or np.isnan(val) or np.isinf(val):
                return 0.0
            return float(val)
        
        # 7. Construct Final Record
        insight_record = {
            "processed_at": int(time.time()),
            "fiat": fiat,
            "asset": asset,
            "avg_price": clean_val(float(df['price'].mean())),
            "best_buy_price": clean_val(float(best_buy)),
            "best_sell_price": clean_val(float(best_sell)),
            "market_spread_pct": round(clean_val(float(spread_pct)), 3),
            
            # Merchant Metrics
            "verified_ratio": adv_insights.get("verified_merchant_ratio"),
            "risky_ads": adv_insights.get("risky_advertiser_count"),
            "top_merchant": adv_insights.get("dominant_advertiser"),
            
            "total_liquidity": total_liq,
            "whale_count": whale_count,
            "p2p_vs_spot_profit_pct": round(clean_val(float(p2p_vs_spot_profit)), 3),
            "fx_rate_gap_pct": clean_val(triangle_profit), # Triangle arb profit
            "order_book_depth": depth_json,
            "risk_level": risk,
            "market_trust_avg": round(clean_val(float(df['trust_score'].mean())), 2)
        }


        self.save_insight(insight_record)
        return insight_record

    def save_insight(self, record):
        """Push processed insights to p2p_insights table."""
        try:
            self.supabase.table("p2p_insights").insert(record).execute()
            logger.info(f"✅ Insight saved for {record['asset']}/{record['fiat']} at {record['best_buy_price']}")
        except Exception as e:
            logger.error(f"❌ Error saving insight: {e}")

    def main(self):
        """Iterates through your target markets and processes everything."""
        markets = [("USDT", "EUR"), ("USDT", "USD")]
        for asset, fiat in markets:
            logger.info(f"Processing insights for {asset}/{fiat}...")
            self.process_market_insights(asset, fiat)
            time.sleep(1) # Prevent API rate limits