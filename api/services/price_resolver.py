from __future__ import annotations

import logging
import os
import time
from functools import lru_cache

import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("SpotPriceResolver")


BINANCE_DIRECT_PAIRS = {
    # fiat → Binance symbol
    "EUR": "EURUSDT",
    "USD": "USDUSDT",
    # Add more as Binance lists them
}

# Fiats that Binance does NOT list — we derive via FX rate
# (1 USDT ≈ 1 USD × FX_rate(USD→FIAT))
DERIVED_VIA_FX = [
    "MAD", "NGN", "EGP", "KES", "GHS", "ZAR",
    "PKR", "INR", "VND", "PHP", "IDR", "THB",
    "MYR", "AED", "SAR", "KWD", "QAR",
    "UAH", "KZT", "UZS", "COP",
]


class SpotPriceResolver:
    """
    Resolves spot_price_in_fiat for any (asset, fiat) pair.
    Results are cached for `cache_ttl` seconds to avoid hammering APIs.
    """

    BINANCE_BASE = "https://api.binance.com/api/v3"
    FX_BASE      = "https://v6.exchangerate-api.com/v6"

    def __init__(self, cache_ttl: int = 300):
        """
        cache_ttl: how long (seconds) to cache resolved prices.
                   Default 300s = 5 minutes (fine for analytics layer).
                   Set lower (60s) if you need fresher data for alerts.
        """
        self.cache_ttl  = cache_ttl
        self.fx_api_key = os.getenv("EXCHANGERATE_API_KEY")
        self._cache: dict[str, tuple[float, float]] = {}  # key → (price, ts)
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    # ─────────────────────────────────────────────────────────────
    # PUBLIC API
    # ─────────────────────────────────────────────────────────────

    def get(self, asset: str, fiat: str) -> float | None:
        """
        Returns spot price of `asset` denominated in `fiat`.
        Examples:
            get("USDT", "EUR")  → 0.9215   (direct Binance pair)
            get("USDT", "MAD")  → 9.9412   (derived: 1 USD × FX rate)
            get("BTC",  "USDT") → 67450.0  (direct Binance pair)
            get("ETH",  "EUR")  → 3120.5   (ETH/USDT × FX rate)
        """
        cache_key = f"{fiat}/{asset}"
        cached = self._from_cache(cache_key)
        if cached is not None:
            return cached

        price = self._resolve(asset, fiat)
        if price is not None:
            self._to_cache(cache_key, price)
        return price

    def get_all(self, fiats: list[str], asset: str = "USDT") -> dict[str, float]:
        """
        Resolve spot price for one asset against multiple fiats.
        Batches Binance calls where possible.
        Returns: {"EUR": 0.9215, "MAD": 9.94, "NGN": 1587.3, ...}
        """
        results: dict[str, float] = {}

        # Split into direct and derived groups
        direct  = [f for f in fiats if f in BINANCE_DIRECT_PAIRS]
        derived = [f for f in fiats if f in DERIVED_VIA_FX or f not in BINANCE_DIRECT_PAIRS]

        # Batch fetch direct pairs from Binance
        if direct and asset == "USDT":
            symbols   = [BINANCE_DIRECT_PAIRS[f] for f in direct]
            prices    = self._binance_batch_ticker(symbols)
            for fiat in direct:
                sym = BINANCE_DIRECT_PAIRS[fiat]
                if sym in prices:
                    results[fiat] = prices[sym]
                    self._to_cache(f"{asset}/{fiat}", prices[sym])

        # Batch fetch FX rates for derived pairs (single API call covers all)
        if derived and self.fx_api_key:
            usdt_usd  = self._usdt_usd_price()    # USDT price in USD (≈ 1.0)
            fx_rates  = self._fx_rates_for("USD")  # 1 USD = X FIAT for all fiats
            for fiat in derived:
                if fiat in fx_rates and usdt_usd:
                    price = usdt_usd * fx_rates[fiat]
                    results[fiat] = round(price, 6)
                    self._to_cache(f"{asset}/{fiat}", price)

        return results

    # ─────────────────────────────────────────────────────────────
    # RESOLUTION LOGIC
    # ─────────────────────────────────────────────────────────────

    def _resolve(self, asset: str, fiat: str) -> float | None:
        """
        Resolution order:
          1. Direct Binance pair (e.g. USDTEUR)
          2. Asset via USDT + FX rate  (e.g. USDT/MAD = USDT_USD × FX)
          3. Asset/USDT on Binance + FX rate (e.g. BTC/EUR = BTCUSDT × USDTEUR)
        """

        # ── PATH A: Direct Binance USDT/FIAT pair ──────────────────
        if asset == "USDT" and fiat in BINANCE_DIRECT_PAIRS:
            price = self._binance_ticker(BINANCE_DIRECT_PAIRS[fiat])
            if price:
                logger.debug(f"PATH A: {fiat}/{asset} = {price} (direct Binance)")
                return price

        # ── PATH B: USDT via FX rate ───────────────────────────────
        if asset == "USDT":
            usdt_usd = self._usdt_usd_price()         # ≈ 1.0
            fx_rate  = self._fx_rate("USD", fiat)      # 1 USD = X FIAT
            if usdt_usd and fx_rate:
                price = usdt_usd * fx_rate
                logger.debug(
                    f"PATH B: {fiat}/{asset} = {usdt_usd} × {fx_rate} = {price:.6f} (FX derived)"
                )
                return round(price, 6)

        # ── PATH C: Non-USDT asset (BTC, ETH, etc.) via USDT ───────
        # Get asset price in USDT, then convert USDT→FIAT
        asset_usdt_symbol = f"{asset}USDT"
        asset_in_usdt = self._binance_ticker(asset_usdt_symbol)
        if asset_in_usdt:
            usdt_in_fiat = self.get("USDT", fiat)    # recursive, cached
            if usdt_in_fiat:
                price = asset_in_usdt * usdt_in_fiat
                logger.debug(
                    f"PATH C: {fiat}/{asset} = {asset_in_usdt} × {usdt_in_fiat} = {price:.6f}"
                )
                return round(price, 6)

        logger.warning(f"Could not resolve spot price for {fiat}/{asset}")
        return None

    # ─────────────────────────────────────────────────────────────
    # BINANCE HELPERS
    # ─────────────────────────────────────────────────────────────

    def _binance_ticker(self, symbol: str) -> float | None:
        """Fetch single ticker price from Binance."""
        try:
            resp = self._session.get(
                f"{self.BINANCE_BASE}/ticker/price",
                params={"symbol": symbol},
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            return float(data["price"])
        except Exception as e:
            logger.warning(f"Binance ticker error ({symbol}): {e}")
            return None

    def _binance_batch_ticker(self, symbols: list[str]) -> dict[str, float]:
        """
        Batch price fetch for multiple symbols.
        Returns: {"USDTEUR": 0.9215, "USDTGBP": 0.792, ...}
        """
        import json
        try:
            resp = self._session.get(
                f"{self.BINANCE_BASE}/ticker/price",
                params={"symbols": json.dumps(symbols)},
                timeout=8,
            )
            resp.raise_for_status()
            return {item["symbol"]: float(item["price"]) for item in resp.json()}
        except Exception as e:
            logger.warning(f"Binance batch ticker error: {e}")
            # Fallback: fetch individually
            result = {}
            for sym in symbols:
                p = self._binance_ticker(sym)
                if p:
                    result[sym] = p
                time.sleep(0.1)
            return result

    def _usdt_usd_price(self) -> float:
        """
        USDT price in USD. Normally ≈ 1.0 but can deviate ±0.2% during stress.
        Uses BUSDUSDT as a proxy when available; falls back to 1.0.
        """
        # Try to get actual USDT/USD price from Binance
        # USDT is quoted as base on Binance in pair like USDTUSDT (not listed)
        # Best proxy: 1/USDCUSDT or just use 1.0 (accurate enough for our use)
        try:
            # Try TUSDUSDT as a stable-stable proxy
            p = self._binance_ticker("USDCUSDT")
            if p and 0.95 < p < 1.05:
                return round(1.0 / p, 6)   # invert: we want USDT in USD
        except Exception:
            pass
        return 1.0   # USDT ≈ 1 USD — safe assumption for P2P analytics

    # ─────────────────────────────────────────────────────────────
    # FX RATE HELPERS
    # ─────────────────────────────────────────────────────────────

    def _fx_rate(self, base: str, target: str) -> float | None:
        """Single FX rate from ExchangeRate-API or Supabase cache."""
        # First try Supabase (if it's been recently stored by FXRateCollector)
        rate = self._fx_from_supabase(base, target)
        if rate:
            return rate
        # Fallback: call API directly
        rates = self._fx_rates_for(base)
        return rates.get(target)

    def _fx_rates_for(self, base: str) -> dict[str, float]:
        """
        Fetch all FX rates for a base currency from ExchangeRate-API.
        Returns: {"EUR": 0.92, "MAD": 9.94, "NGN": 1587.3, ...}
        """
        if not self.fx_api_key:
            logger.error("EXCHANGERATE_API_KEY not set — cannot fetch FX rates")
            return {}
        try:
            resp = self._session.get(
                f"{self.FX_BASE}/{self.fx_api_key}/latest/{base}",
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("result") != "success":
                logger.error(f"FX API error: {data.get('error-type')}")
                return {}
            return data.get("conversion_rates", {})
        except Exception as e:
            logger.error(f"FX rate fetch error: {e}")
            return {}

    def _fx_from_supabase(self, base: str, target: str) -> float | None:
        """
        Read latest FX rate from Supabase fx_rates table (stored by collector).
        Avoids hitting ExchangeRate-API on every analytics call.
        Returns None if no recent rate found (older than 1h).
        """
        try:
            from supabase import create_client
            sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
            res = (
                sb.table("fx_rates")
                .select("rate, collected_at")
                .eq("base_currency",   base)
                .eq("target_currency", target)
                .order("collected_at", desc=True)
                .limit(1)
                .execute()
            )
            if res.data:
                from datetime import datetime, timezone, timedelta
                row = res.data[0]
                age = datetime.now(timezone.utc) - datetime.fromisoformat(row["collected_at"])
                if age < timedelta(hours=2):      # accept rates up to 2h old
                    return float(row["rate"])
        except Exception as e:
            logger.debug(f"Supabase FX lookup failed: {e}")
        return None

    # ─────────────────────────────────────────────────────────────
    # CACHE
    # ─────────────────────────────────────────────────────────────

    def _from_cache(self, key: str) -> float | None:
        if key in self._cache:
            price, ts = self._cache[key]
            if time.time() - ts < self.cache_ttl:
                return price
            del self._cache[key]
        return None

    def _to_cache(self, key: str, price: float):
        self._cache[key] = (price, time.time())

    def clear_cache(self):
        self._cache.clear()


# ─────────────────────────────────────────────────────────────────────────────
# CONVENIENCE: pre-wired call for analytics_engine.p2p_premium()
# ─────────────────────────────────────────────────────────────────────────────

def resolve_spot_for_premium(
    asset: str,
    fiat: str,
    resolver: SpotPriceResolver | None = None,
) -> float | None:
    """
    One-liner to get the spot price ready to pass into engine.p2p_premium().

    Usage:
        from spot_price_resolver import resolve_spot_for_premium
        from analytics_engine import AnalyticsEngine

        engine  = AnalyticsEngine()
        spot    = resolve_spot_for_premium("USDT", "MAD")
        premium = engine.p2p_premium("USDT", "MAD", spot)
    """
    r = resolver or SpotPriceResolver()
    return r.get(asset, fiat)


# ─────────────────────────────────────────────────────────────────────────────
# CLI / QUICK TEST
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Resolve spot prices")
    parser.add_argument("--asset",  default="USDT")
    parser.add_argument("--fiats",  nargs="+",
                        default=["EUR","MAD","NGN","TRY","BRL","GBP","EGP"])
    args = parser.parse_args()

    resolver = SpotPriceResolver()

    print(f"\nSpot prices for {args.asset}:\n{'─'*35}")
    prices = resolver.get_all(args.fiats, asset=args.asset)
    for fiat, price in sorted(prices.items()):
        print(f"  {args.asset}/{fiat:<6}  →  {price:.6f}")

    # Show how to wire into analytics engine
    print(f"\n{'─'*35}")
    print("Wiring into analytics engine:\n")
    print("  from spot_price_resolver import SpotPriceResolver")
    print("  from analytics_engine import AnalyticsEngine\n")
    print("  resolver = SpotPriceResolver()")
    print("  engine   = AnalyticsEngine()\n")
    for fiat, price in list(prices.items())[:3]:
        print(f"  engine.p2p_premium('USDT', '{fiat}', {price:.6f})")