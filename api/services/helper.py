from __future__ import annotations
 
import os
from typing import Literal
 
import pandas as pd
from supabase import create_client, Client
from dotenv import load_dotenv


class Helper:
    
    Timeframe  = Literal["1h", "12h", "24h"]
    TradeType  = Literal["BUY", "SELL"]
    
    _VIEW = {
        "1h":  "mv_market_1h",
        "12h": "mv_market_12h",
        "24h": "mv_market_24h",
    }
    
    


    def __init__(self):
        load_dotenv()
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY"),
        )

    
    def _fetch(
        self,
        tf: Timeframe,
        asset: str | None = None,
        fiat:  str | None = None,
        trade_type: TradeType | None = None,
    ) -> pd.DataFrame:
        """Fetch one view with optional filters."""
        q = self.supabase.table(self._VIEW[tf]).select("*")
        if asset:      q = q.eq("asset", asset)
        if fiat:       q = q.eq("fiat", fiat)
        if trade_type: q = q.eq("trade_type", trade_type)
        res = q.execute()
        df = pd.DataFrame(res.data or [])
        for col in ["avg_price","best_price","worst_price","liquidity","volatility"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        if "adv_count" in df.columns:
            df["adv_count"] = pd.to_numeric(df["adv_count"], errors="coerce").astype("Int64")
        return df

    def _fetch_both_sides(
        self, tf: Timeframe, asset: str, fiat: str
    ) -> tuple[pd.Series | None, pd.Series | None]:
        """Return (buy_row, sell_row) Series for a specific pair and timeframe."""
        df = self._fetch(tf, asset=asset, fiat=fiat)
        if df.empty:
            return None, None
        buy_df  = df[df["trade_type"] == "BUY"]
        sell_df = df[df["trade_type"] == "SELL"]
        buy  = buy_df.iloc[0]  if not buy_df.empty  else None
        sell = sell_df.iloc[0] if not sell_df.empty else None
        return buy, sell
 
    def _all_windows(
        self, asset: str, fiat: str, trade_type: TradeType
    ) -> pd.DataFrame:
        """
        Stack all 3 timeframes into one DataFrame with a 'window' column.
        Useful for cross-window comparison methods.
        """
        frames = []
        for tf in ("1h", "12h", "24h"):
            df = self._fetch(tf, asset=asset, fiat=fiat, trade_type=trade_type)
            if not df.empty:
                df["window"] = tf
                frames.append(df)
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
 
    def _safe(self, val, default=0.0) -> float:
        try:
            return float(val) if val is not None and not pd.isna(val) else default
        except Exception:
            return default
