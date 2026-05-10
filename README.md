# Binance P2P Analytics Engine

A Python analytics engine for analyzing Binance P2P market data.

Designed for:

- P2P traders
- Arbitrage traders
- Market makers
- Quant dashboards
- Data analytics platforms
- Market intelligence tools

---

# Data Extraction

The binance P2P API used to extract data, using Request Fingerprint Rotation, Adaptive Rate Limiting, Exponential Backoff Retry. 
The Extractor store a snapshot of the market every 15 minutes via GitHub Actions, clean and sotre data to Supabase PostgreSQL Database

| Field               | Type           | Description                                                    | Example                    | Usage                                     |
| ------------------- | -------------- | -------------------------------------------------------------- | -------------------------- | ----------------------------------------- |
| `snapshot_time`     | datetime       | Timestamp when the ad snapshot was collected                   | `2026-05-10 14:00:00`      | Time-series analysis, historical tracking |
| `adv_no`            | string         | Unique Binance P2P advertisement ID                            | `1234567890`               | Ad identification, deduplication          |
| `asset`             | string         | Cryptocurrency being traded                                    | `USDT`                     | Pair grouping/filtering                   |
| `fiat`              | string         | Fiat currency used in the trade                                | `EUR`                      | Regional market analysis                  |
| `trade_type`        | string         | Side of the ad (`BUY` or `SELL`)                               | `BUY`                      | Spread calculations                       |
| `price`             | float          | Price per unit of crypto in fiat                               | `0.9245`                   | Pricing analytics                         |
| `surplus_amount`    | float          | Remaining available crypto quantity                            | `5000`                     | Liquidity estimation                      |
| `tradable_quantity` | float          | Tradable quantity currently available                          | `4800`                     | Market depth analysis                     |
| `min_amount`        | float          | Minimum fiat amount allowed for the trade                      | `10`                       | User trade constraints                    |
| `max_amount`        | float          | Maximum fiat amount allowed for the trade                      | `5000`                     | Large order analysis                      |
| `payment_methods`   | list[string]   | Accepted payment methods                                       | `['SEPA', 'REVOLUT']`      | Payment segmentation                      |
| `merchant_id`       | string         | Binance internal merchant/user ID                              | `987654321`                | Merchant tracking                         |
| `merchant_name`     | string         | Merchant nickname                                              | `BestTraderEU`             | Display/UI                                |
| `month_orders`      | integer        | Number of completed orders in last 30 days                     | `1250`                     | Merchant activity analysis                |
| `month_finish_rate` | float          | Merchant order completion rate (%)                             | `98.5`                     | Reliability scoring                       |
| `positive_rate`     | float          | Positive feedback/reputation score (%)                         | `99.2`                     | Trust analysis                            |
| `user_grade`        | string         | Binance merchant grade/rank                                    | `Gold`                     | Merchant classification                   |
| `vip_level`         | integer/string | Binance VIP level                                              | `3`                        | Premium merchant identification           |
| `active_seconds`    | integer        | Seconds since merchant last active                             | `120`                      | Online activity monitoring                |
| `badges`            | list[string]   | Binance merchant badges                                        | `['verified', 'merchant']` | Trust/reputation system                   |
| `pay_time_limit`    | integer        | Time limit allowed for payment completion (minutes)            | `15`                       | Transaction speed analysis                |
| `opportunity_score` | float          | Internal calculated score evaluating trade opportunity quality | `82.5`                     | Opportunity ranking/filtering             |


# Data storage

Supabase used to store raw data, and aggregate data stored in Materialized View for every timeframe, the partman_pg used to partion table, and pg_cron used to run cron job to refresh views.

## Aggregated Data

| Column        | Description                      |
| ------------- | -------------------------------- |
| `asset`       | Crypto asset (USDT, BTC, ETH...) |
| `fiat`        | Fiat currency (EUR, USD...)      |
| `trade_type`  | BUY or SELL                      |
| `avg_price`   | Average ad price                 |
| `best_price`  | Best available price             |
| `worst_price` | Worst available price            |
| `liquidity`   | Total tradable quantity          |
| `volatility`  | Standard deviation of prices     |
| `adv_count`   | Number of active ads             |
| `window`      | Aggregation window               |


# Analytics API

A FastAPI application used to read data from Supabase database and compute market analytics metrics, The api provides:

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


# Data visualization

Streamlit used to create a simple dashboard, request data from API and create charts