create materialized view mv_market_1h as
select
    asset,
    fiat,
    trade_type,

    avg(price) as avg_price,
    min(price) as best_price,
    max(price) as worst_price,

    sum(tradable_quantity) as liquidity,
    stddev(price) as volatility,

    count(*) as adv_count

from p2p_market_data
where snapshot_time >= now() - interval '1 hour'
group by asset, fiat, trade_type;

create materialized view mv_market_12h as
select
    asset,
    fiat,
    trade_type,

    avg(price) as avg_price,
    min(price) as best_price,
    max(price) as worst_price,

    sum(tradable_quantity) as liquidity,
    stddev(price) as volatility,

    count(*) as adv_count

from p2p_market_data
where snapshot_time >= now() - interval '12 hour'
group by asset, fiat, trade_type;

create materialized view mv_market_24h as
select
    asset,
    fiat,
    trade_type,

    avg(price) as avg_price,
    min(price) as best_price,
    max(price) as worst_price,

    sum(tradable_quantity) as liquidity,
    stddev(price) as volatility,

    count(*) as adv_count

from p2p_market_data
where snapshot_time >= now() - interval '24 hour'
group by asset, fiat, trade_type;

create index mv1h_idx on mv_market_1h (asset, fiat, trade_type);
create index mv6h_idx on mv_market_12h (asset, fiat, trade_type);
create index mv1d_idx on mv_market_24h (asset, fiat, trade_type);