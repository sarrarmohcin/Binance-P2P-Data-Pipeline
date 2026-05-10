from services.helper import Helper
from services.price_resolver import SpotPriceResolver
import pandas as pd

class Market:
    
    # Estimated round-trip fee assumption (0.1% per leg)
    DEFAULT_FEE_PCT = 0.20
    
    def __init__(self):
        self.helper = Helper()
        self.resolver = SpotPriceResolver()
    
    # ──────────────────────────────────────────────────────────────
    # 1. MARKET SNAPSHOT
    # ──────────────────────────────────────────────────────────────
    # HOW: Direct read of the materialized view for one timeframe.
    # TRADERS USE IT: The "what is the market doing right now" baseline —
    #   best available price, total supply, how many active ads.
    # DASHBOARD: KPI cards row at top of any pair page.
    #   best_price → large number with green/red arrow vs 12h
    #   liquidity  → total USDT available
    #   adv_count  → market depth indicator
    #   volatility → color badge: low/medium/high
    # ──────────────────────────────────────────────────────────────

    def market_snapshot(self, asset: str, fiat: str, tf: str = "1h") -> dict:
        """Single-pair market snapshot for a given window."""
        df = self.helper._fetch(tf, asset=asset, fiat=fiat)
        if df.empty:
            return {}
 
        result = {}
        for _, row in df.iterrows():
            side = row["trade_type"]
            result[side] = {
                "avg_price":   round(self.helper._safe(row["avg_price"]),   6),
                "best_price":  round(self.helper._safe(row["best_price"]),  6),
                "worst_price": round(self.helper._safe(row["worst_price"]), 6),
                "liquidity":   round(self.helper._safe(row["liquidity"]),   2),
                "volatility":  round(self.helper._safe(row["volatility"]),  6),
                "adv_count":   int(self.helper._safe(row["adv_count"])),
                "window":      tf,
            }
        return result

    def spread(self, asset: str, fiat: str, tf: str = "1h") -> dict:
        """Spread metrics for a pair from one timeframe."""
        buy, sell = self.helper._fetch_both_sides(tf, asset, fiat)
        if buy is None or sell is None:
            return {}
 
        best_buy    = self.helper._safe(buy["best_price"])
        best_sell   = self.helper._safe(sell["best_price"])
        avg_buy     = self.helper._safe(buy["avg_price"])
        avg_sell    = self.helper._safe(sell["avg_price"])
 
        spread_abs     = best_sell - best_buy
        spread_pct     = spread_abs / best_buy * 100 if best_buy else 0
 
        avg_spread_abs = avg_sell - avg_buy
        avg_spread_pct = avg_spread_abs / avg_buy * 100 if avg_buy else 0
 
        net_pct        = spread_pct - self.DEFAULT_FEE_PCT
 
        return {
            "asset": asset, "fiat": fiat, "window": tf,
            # Top-of-book (aggressive, can be noisy)
            "best_buy_price":    round(best_buy,      6),
            "best_sell_price":   round(best_sell,     6),
            "spread_abs":        round(spread_abs,    6),
            "spread_pct":        round(spread_pct,    4),
            "net_pct":           round(net_pct,       4),
            # Average-based (smoother, more reliable signal)
            "avg_buy_price":     round(avg_buy,       6),
            "avg_sell_price":    round(avg_sell,      6),
            "avg_spread_abs":    round(avg_spread_abs,6),
            "avg_spread_pct":    round(avg_spread_pct,4),
            # Signal
            "is_profitable":     net_pct > 0,
            "tier": (
                "extreme" if spread_pct > 3.0 else
                "high"    if spread_pct > 1.5 else
                "medium"  if spread_pct > 0.5 else
                "low"     if spread_pct > 0.2 else
                "flat"
            ),
        }
 
    def spread_all_windows(self, asset: str, fiat: str) -> list[dict]:
        """
        Spread across all 3 windows — reveals if spread is widening or
        compressing over time.
 
        HOW: Compare spread_pct at 1h vs 12h vs 24h.
          - spread_1h > spread_24h → spread is WIDENING (opportunity opening)
          - spread_1h < spread_24h → spread is COMPRESSING (arb being closed)
 
        DASHBOARD: 3-column comparison table or grouped bar chart.
          Arrow badge: spread_1h vs spread_24h → ↑ widening / ↓ compressing.
        """
        results = [self.spread(asset, fiat, tf) for tf in ("1h", "12h", "24h")]
        results = [r for r in results if r]
 
        if len(results) >= 2:
            s1h  = results[0].get("spread_pct", 0)
            s24h = results[-1].get("spread_pct", 0)
            delta = s1h - s24h
            trend = "widening" if delta > 0.05 else "compressing" if delta < -0.05 else "stable"
            for r in results:
                r["trend"]        = trend
                r["delta_vs_24h"] = round(delta, 4)
 
        return results
 
    # ──────────────────────────────────────────────────────────────
    # 3. VOLATILITY ANALYSIS
    # ──────────────────────────────────────────────────────────────
    # HOW: volatility = STDDEV(price) from the view — how spread-out
    #   prices are across all active ads in the window.
    #   volatility_ratio = volatility / avg_price × 100 (normalized %)
    #   Cross-window: compare 1h vs 24h volatility to detect spikes.
    # TRADERS USE IT:
    #   High volatility = merchants disagree on price → pricing chaos,
    #   some ads mispriced → manual scanning opportunity.
    #   Low volatility = tight cluster → competitive, efficient market.
    # DASHBOARD: Volatility badge (Low/Med/High) on pair card.
    #   Trend: "volatility spiked 3× in last 1h vs 24h avg".
    # ──────────────────────────────────────────────────────────────
 
    def volatility_analysis(self, asset: str, fiat: str, trade_type: str = "BUY") -> dict:
        """Volatility comparison across all windows."""
        df = self.helper._all_windows(asset, fiat, trade_type)
        if df.empty:
            return {}
 
        result = {}
        for _, row in df.iterrows():
            w     = row["window"]
            vol   = self.helper._safe(row["volatility"])
            avg   = self.helper._safe(row["avg_price"])
            ratio = vol / avg * 100 if avg else 0
 
            result[w] = {
                "volatility":       round(vol,   6),
                "volatility_ratio": round(ratio, 4),
                "avg_price":        round(avg,   6),
                "adv_count":        int(self.helper._safe(row["adv_count"])),
                "label": (
                    "high"   if ratio > 1.0 else
                    "medium" if ratio > 0.3 else
                    "low"
                ),
            }
 
        # Spike detection: 1h vol vs 24h vol
        if "1h" in result and "24h" in result:
            r1h  = result["1h"]["volatility_ratio"]
            r24h = result["24h"]["volatility_ratio"]
            spike = r1h / r24h if r24h else 1.0
            result["spike"] = {
                "factor":    round(spike, 2),
                "is_spike":  spike > 2.0,
                "direction": "up" if spike > 1.0 else "down",
            }
 
        return result
 
    # ──────────────────────────────────────────────────────────────
    # 4. PRICE MOMENTUM (cross-window drift)
    # ──────────────────────────────────────────────────────────────
    # HOW: Compare avg_price across windows.
    #   momentum = avg_price_1h - avg_price_24h
    #   momentum_pct = momentum / avg_price_24h × 100
    # TRADERS USE IT: If 1h avg is 1.5% above 24h avg → price is rising.
    #   Sellers should act now before it drops back.
    #   Buyers should wait — price may revert.
    # DASHBOARD: Momentum arrow on pair card with % value.
    #   1h vs 12h vs 24h avg_price as a 3-point mini trend line.
    # ──────────────────────────────────────────────────────────────
 
    def price_momentum(self, asset: str, fiat: str, trade_type: str = "BUY") -> dict:
        """Price drift: how much has avg_price moved from 24h baseline to now."""
        df = self.helper._all_windows(asset, fiat, trade_type)
        if df.empty:
            return {}
 
        prices = {}
        for _, row in df.iterrows():
            prices[row["window"]] = self.helper._safe(row["avg_price"])
 
        p1h  = prices.get("1h",  0)
        p12h = prices.get("12h", 0)
        p24h = prices.get("24h", 0)
 
        mom_vs_24h = (p1h - p24h) / p24h * 100 if p24h else 0
        mom_vs_12h = (p1h - p12h) / p12h * 100 if p12h else 0
 
        return {
            "asset": asset, "fiat": fiat, "trade_type": trade_type,
            "price_1h":              round(p1h,  6),
            "price_12h":             round(p12h, 6),
            "price_24h":             round(p24h, 6),
            "momentum_vs_24h_pct":   round(mom_vs_24h, 4),
            "momentum_vs_12h_pct":   round(mom_vs_12h, 4),
            "direction": (
                "up"   if mom_vs_24h >  0.1 else
                "down" if mom_vs_24h < -0.1 else
                "flat"
            ),
            "signal": (
                "strong_up"   if mom_vs_24h >  1.0 else
                "strong_down" if mom_vs_24h < -1.0 else
                "mild_up"     if mom_vs_24h >  0.3 else
                "mild_down"   if mom_vs_24h < -0.3 else
                "neutral"
            ),
        }
 
    # ──────────────────────────────────────────────────────────────
    # 5. LIQUIDITY ANALYSIS
    # ──────────────────────────────────────────────────────────────
    # HOW: liquidity = SUM(tradable_quantity) across all ads in window.
    #   liquidity_per_ad = liquidity / adv_count → avg ad size.
    #   Cross-window: 1h liquidity vs 24h → is supply growing or draining?
    # TRADERS USE IT:
    #   High 1h liquidity = market is active, large orders fillable now.
    #   1h << 24h → supply is being consumed faster than restocked.
    #   liquidity_per_ad → few large merchants vs many small ones.
    # DASHBOARD: Liquidity bar with fill % relative to 24h max.
    #   "Available now: 234,500 USDT across 18 ads"
    #   Trend: ↑ supply growing / ↓ draining.
    # ──────────────────────────────────────────────────────────────
 
    def liquidity_analysis(self, asset: str, fiat: str, trade_type: str = "BUY") -> dict:
        """Liquidity depth comparison across all windows."""
        df = self.helper._all_windows(asset, fiat, trade_type)
        if df.empty:
            return {}
 
        windows = {}
        for _, row in df.iterrows():
            w   = row["window"]
            liq = self.helper._safe(row["liquidity"])
            cnt = max(int(self.helper._safe(row["adv_count"])), 1)
            windows[w] = {
                "liquidity":        round(liq, 2),
                "adv_count":        cnt,
                "liquidity_per_ad": round(liq / cnt, 2),
            }
 
        liq_1h  = windows.get("1h",  {}).get("liquidity", 0)
        liq_24h = windows.get("24h", {}).get("liquidity", 0)
 
        trend = "growing"  if liq_1h > liq_24h * 0.12 else \
                "draining" if liq_1h < liq_24h * 0.06 else \
                "stable"
 
        return {
            "asset": asset, "fiat": fiat, "trade_type": trade_type,
            "windows":       windows,
            "trend":         trend,
            "fill_ratio_1h": round(liq_1h / liq_24h * 100, 2) if liq_24h else 0,
        }
 
    # ──────────────────────────────────────────────────────────────
    # 6. MARKET EFFICIENCY SCORE  (0–100)
    # ──────────────────────────────────────────────────────────────
    # HOW: Composite of 4 signals from the 1h view:
    #   spread_score     = tight spread → high score
    #   liquidity_score  = more supply → high score
    #   depth_score      = more ads → high score
    #   stability_score  = low volatility → high score
    # TRADERS USE IT: Quick "is this market worth trading right now?"
    #   High score = liquid, tight, stable → efficient execution.
    #   Low score  = wide spread + thin + volatile → risky/expensive.
    # DASHBOARD: Radial gauge 0-100 with 4 component bars.
    #   Color: <40 red · 40-70 amber · >70 green.
    # ──────────────────────────────────────────────────────────────
 
    def market_efficiency_score(self, asset: str, fiat: str) -> dict:
        """Composite market quality score from 1h view."""
        sp  = self.spread(asset, fiat, "1h")
        buy, _ = self.helper._fetch_both_sides("1h", asset, fiat)
        if not sp or buy is None:
            return {}
 
        liq       = self.helper._safe(buy["liquidity"])
        adv       = self.helper._safe(buy["adv_count"])
        vol_ratio = self.helper._safe(buy["volatility"]) / max(self.helper._safe(buy["avg_price"]), 1) * 100
 
        spread_score    = max(0, 100 - sp["spread_pct"] * 20)
        liquidity_score = min(100, liq / 10_000 * 100)
        depth_score     = min(100, adv / 20 * 100)
        stability_score = max(0, 100 - vol_ratio * 50)
 
        total = (
            spread_score    * 0.35 +
            liquidity_score * 0.30 +
            depth_score     * 0.20 +
            stability_score * 0.15
        )
 
        return {
            "asset": asset, "fiat": fiat,
            "score":            round(total, 1),
            "grade":            "A" if total >= 80 else "B" if total >= 60 else "C" if total >= 40 else "D",
            "spread_score":     round(spread_score,    1),
            "liquidity_score":  round(liquidity_score, 1),
            "depth_score":      round(depth_score,     1),
            "stability_score":  round(stability_score, 1),
            "spread_pct":       sp["spread_pct"],
            "liquidity":        round(liq, 2),
            "adv_count":        int(adv),
            "volatility_ratio": round(vol_ratio, 4),
        }
 
    # ──────────────────────────────────────────────────────────────
    # 7. OPPORTUNITY ALERTS
    # ──────────────────────────────────────────────────────────────
    # HOW: Scan every (asset, fiat) pair in the 1h view.
    #   Flag pairs where spread_pct > threshold AND net_pct > 0.
    #   Rank by net_pct DESC.
    # TRADERS USE IT: "Show me what's worth trading right now."
    #   Saves scanning 50 pairs manually — one ranked feed.
    # DASHBOARD: Alert feed panel, refreshes every 15min.
    #   Each row: pair · spread % · net % · tier badge · liquidity.
    # ──────────────────────────────────────────────────────────────
 
    def opportunity_alerts(
        self,
        min_spread_pct: float = 0.3,
        min_liquidity:  float = 1_000.0,
    ) -> pd.DataFrame:
        """All profitable arb opportunities across every tracked pair."""
        df = self.helper._fetch("1h")
        if df.empty:
            return pd.DataFrame()
 
        pairs = df[["asset", "fiat"]].drop_duplicates().values.tolist()
        alerts = []
 
        for asset, fiat in pairs:
            sp = self.spread(asset, fiat, "1h")
            if not sp or sp["spread_pct"] < min_spread_pct:
                continue
 
            buy_rows = df[
                (df["asset"] == asset) &
                (df["fiat"]  == fiat)  &
                (df["trade_type"] == "BUY")
            ]
            if buy_rows.empty:
                continue
            buy_liq = self.helper._safe(buy_rows.iloc[0]["liquidity"])
            if buy_liq < min_liquidity:
                continue
 
            sp["buy_liquidity"] = round(buy_liq, 2)
            alerts.append(sp)
 
        if not alerts:
            return pd.DataFrame()
 
        return (
            pd.DataFrame(alerts)
            .sort_values("net_pct", ascending=False)
            .reset_index(drop=True)
        )
 
    # ──────────────────────────────────────────────────────────────
    # 8. CROSS-WINDOW COMPARISON TABLE
    # ──────────────────────────────────────────────────────────────
    # HOW: Pull all 3 windows for a pair, side by side.
    #   Show how avg_price, liquidity, spread, volatility evolved.
    # TRADERS USE IT: Single table that tells the whole story of a
    #   pair across 1h / 12h / 24h without clicking through tabs.
    # DASHBOARD: 3-column stat table on pair detail page.
    # ──────────────────────────────────────────────────────────────
 
    def cross_window_table(self, asset: str, fiat: str) -> pd.DataFrame:
        """Side-by-side comparison of all metrics across 3 windows."""
        rows = []
        for tf in ("1h", "12h", "24h"):
            buy, sell = self.helper._fetch_both_sides(tf, asset, fiat)
            sp = self.spread(asset, fiat, tf)
            if buy is None:
                continue
            rows.append({
                "window":     tf,
                "buy_avg":    round(self.helper._safe(buy["avg_price"]),  6),
                "sell_avg":   round(self.helper._safe(sell["avg_price"]), 6) if sell is not None else None,
                "spread_pct": sp.get("spread_pct"),
                "net_pct":    sp.get("net_pct"),
                "buy_liq":    round(self.helper._safe(buy["liquidity"]),  2),
                "sell_liq":   round(self.helper._safe(sell["liquidity"]), 2) if sell is not None else None,
                "buy_ads":    int(self.helper._safe(buy["adv_count"])),
                "sell_ads":   int(self.helper._safe(sell["adv_count"])) if sell is not None else None,
                "volatility": round(self.helper._safe(buy["volatility"]), 6),
            })
        return pd.DataFrame(rows)
 
    # ──────────────────────────────────────────────────────────────
    # 9. MARKET LEADERBOARD
    # ──────────────────────────────────────────────────────────────
    # HOW: Compute efficiency_score for every pair → rank.
    #   Also compute momentum and spread tier for each.
    # TRADERS USE IT: Homepage "best markets right now" ranked list.
    # DASHBOARD: Sortable table/card grid. Default sort: score DESC.
    #   Columns: pair · score · grade · spread · liquidity · momentum.
    # ──────────────────────────────────────────────────────────────
 
    def leaderboard(self) -> pd.DataFrame:
        """Ranked leaderboard of all tracked markets."""
        df = self.helper._fetch("1h")
        if df.empty:
            return pd.DataFrame()
 
        pairs = df[["asset", "fiat"]].drop_duplicates().values.tolist()
        rows  = []
 
        for asset, fiat in pairs:
            score = self.market_efficiency_score(asset, fiat)
            sp    = self.spread(asset, fiat, "1h")
            mom   = self.price_momentum(asset, fiat, "BUY")
            if not score:
                continue
            rows.append({
                "pair":            f"{asset}/{fiat}",
                "asset":           asset,
                "fiat":            fiat,
                "score":           score.get("score"),
                "grade":           score.get("grade"),
                "spread_pct":      sp.get("spread_pct"),
                "net_pct":         sp.get("net_pct"),
                "tier":            sp.get("tier"),
                "liquidity":       score.get("liquidity"),
                "adv_count":       score.get("adv_count"),
                "momentum_pct":    mom.get("momentum_vs_24h_pct"),
                "momentum_signal": mom.get("signal"),
            })
 
        if not rows:
            return pd.DataFrame()
 
        return (
            pd.DataFrame(rows)
            .sort_values("score", ascending=False)
            .reset_index(drop=True)
        )
 
    # ──────────────────────────────────────────────────────────────
    # 10. P2P PREMIUM vs SPOT  (requires spot_price arg)
    # ──────────────────────────────────────────────────────────────
    # HOW: Uses avg_price from 1h view vs caller-supplied spot price.
    #   premium_pct = (p2p_avg - spot) / spot × 100
    #   best_premium = (p2p_best - spot) / spot × 100
    # TRADERS USE IT: Quantify local demand premium. > 2% = strong
    #   local demand → sellers can charge more. < 0% = rare discount.
    # DASHBOARD: Premium gauge per fiat. Map view: country color-coded
    #   by premium tier.
    # ──────────────────────────────────────────────────────────────
 
    def p2p_premium(
        self,
        asset: str,
        fiat: str,
        spot_price_in_fiat: float,
        trade_type: str = "BUY",
        tf: str = "1h",
    ) -> dict:
        """P2P price premium over spot for one pair."""
        df = self.helper._fetch(tf, asset=asset, fiat=fiat, trade_type=trade_type)
        if df.empty or spot_price_in_fiat <= 0:
            return {}
 
        row  = df.iloc[0]
        avg  = self.helper._safe(row["avg_price"])
        best = self.helper._safe(row["best_price"])
 
        avg_premium  = (avg  - spot_price_in_fiat) / spot_price_in_fiat * 100
        best_premium = (best - spot_price_in_fiat) / spot_price_in_fiat * 100
 
        return {
            "asset": asset, "fiat": fiat, "trade_type": trade_type, "window": tf,
            "p2p_avg_price":    round(avg,  6),
            "p2p_best_price":   round(best, 6),
            "spot_price":       round(spot_price_in_fiat, 6),
            "avg_premium_pct":  round(avg_premium,  4),
            "best_premium_pct": round(best_premium, 4),
            "tier": (
                "extreme" if avg_premium > 5.0  else
                "high"    if avg_premium > 2.0  else
                "mild"    if avg_premium > 0.5  else
                "at_par"  if avg_premium > -0.5 else
                "discount"
            ),
        }

    
    # ──────────────────────────────────────────────────────────────
    # 11. DASHBOARD SUMMARY KPIs  (one-call bundle)
    # ──────────────────────────────────────────────────────────────
 
    def summary_kpis(self, asset: str, fiat: str) -> dict:
        """
        All headline metrics for a pair's dashboard page in one call.
        Populates the top KPI card row without multiple round-trips.
 
        Args:
            resolver: optional SpotPriceResolver instance.
                      If provided, premium vs spot is included automatically.
 
        Usage:
            # Without premium (no external APIs needed)
            kpis = engine.summary_kpis("USDT", "EUR")
 
            # With premium (requires Binance Spot + ExchangeRate-API)
            from spot_price_resolver import SpotPriceResolver
            resolver = SpotPriceResolver()
            kpis = engine.summary_kpis("USDT", "EUR", resolver=resolver)
        """
        sp       = self.spread(asset, fiat, "1h")
        sp_trend = self.spread_all_windows(asset, fiat)
        mom      = self.price_momentum(asset, fiat, "BUY")
        liq      = self.liquidity_analysis(asset, fiat, "BUY")
        score    = self.market_efficiency_score(asset, fiat)
 
        # Auto-resolve spot premium when resolver is available
        premium_data: dict = {}
        if self.resolver is not None:
            spot = self.resolver.get(asset, fiat)
            if spot:
                premium_data = self.p2p_premium(asset, fiat, spot)
 
        return {
            "pair":               f"{asset}/{fiat}",
            "asset":              asset,
            "fiat":               fiat,
            # Price
            "best_buy_price":     sp.get("best_buy_price"),
            "best_sell_price":    sp.get("best_sell_price"),
            # Spread
            "spread_pct":         sp.get("spread_pct"),
            "avg_spread_pct":     sp.get("avg_spread_pct"),
            "net_pct":            sp.get("net_pct"),
            "spread_tier":        sp.get("tier"),
            "spread_trend":       sp_trend[0].get("trend")        if sp_trend else None,
            "spread_delta_24h":   sp_trend[0].get("delta_vs_24h") if sp_trend else None,
            # Momentum
            "price_momentum_pct": mom.get("momentum_vs_24h_pct"),
            "price_signal":       mom.get("signal"),
            # Liquidity
            "liquidity_1h":       liq.get("windows", {}).get("1h", {}).get("liquidity"),
            "liquidity_trend":    liq.get("trend"),
            "adv_count":          liq.get("windows", {}).get("1h", {}).get("adv_count"),
            # Score
            "efficiency_score":   score.get("score"),
            "grade":              score.get("grade"),
            # Premium vs spot (only populated when resolver is passed)
            "spot_price":         premium_data.get("spot_price"),
            "avg_premium_pct":    premium_data.get("avg_premium_pct"),
            "best_premium_pct":   premium_data.get("best_premium_pct"),
            "premium_tier":       premium_data.get("tier"),
        }



# Usage
if __name__ == "__main__":
    market = Market()
    asset = "USDT"
    fiat = "EUR"
    tf = "24h"
    side = "BUY"
    min_spread = 0.3


    data = market.market_snapshot(asset, fiat, tf)
    print(data)
    
    market.market_snapshot(asset, fiat, tf)
    market.spread(asset, fiat, tf)
    market.spread_all_windows(asset, fiat)
    market.volatility_analysis(asset, fiat, side)
    market.price_momentum(asset, fiat, side)
    market.liquidity_analysis(asset, fiat, side)
    market.market_efficiency_score(asset, fiat)
    market.opportunity_alerts(min_spread_pct=min_spread)
    market.cross_window_table(asset, fiat)
    market.leaderboard()
    market.summary_kpis(asset, fiat)
