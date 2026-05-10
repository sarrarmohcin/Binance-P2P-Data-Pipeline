# Binance P2P Analytics Engine

A Python analytics engine for analyzing Binance P2P market data across multiple time windows (`1h`, `12h`, `24h`).

The engine provides:

- Market snapshots
- Spread analysis
- Volatility analysis
- Price momentum detection
- Liquidity tracking
- Market efficiency scoring
- Arbitrage opportunity alerts
- P2P premium vs spot analysis
- Cross-window comparisons
- Market leaderboards
- Dashboard-ready KPIs

Designed for:

- P2P traders
- Arbitrage traders
- Market makers
- Quant dashboards
- Data analytics platforms
- Market intelligence tools

---

# Features

## Multi-Window Analytics

All analytics can be computed across:

- `1h` → short-term market state
- `12h` → medium-term trend
- `24h` → long-term baseline

This allows detection of:

- Spread widening/compression
- Volatility spikes
- Liquidity growth/drain
- Price momentum
- Market regime shifts

---

# Architecture

```text
Market
├── Helper
│   ├── Fetch aggregated market views
│   ├── Safe numeric conversion
│   └── Multi-window queries
│
├── SpotPriceResolver
│   ├── Resolve spot market prices
│   └── Convert prices into fiat
│
└── Analytics Methods
    ├── Spread analysis
    ├── Volatility analysis
    ├── Momentum analysis
    ├── Liquidity analysis
    ├── Efficiency scoring
    ├── Opportunity scanning
    └── Premium calculations