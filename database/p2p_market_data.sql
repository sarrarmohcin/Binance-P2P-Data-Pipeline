/* Table creation */
create table p2p_market_data (
    id bigserial,
    snapshot_time timestamptz not null,

    adv_no text,
    asset text,
    fiat text,
    trade_type text,

    price numeric,
    tradable_quantity numeric,
    surplus_amount numeric,

    min_amount numeric,
    max_amount numeric,

    payment_methods jsonb,

    merchant_id text,
    merchant_name text,

    month_orders int,
    month_finish_rate numeric,
    positive_rate numeric,

    user_grade int,
    vip_level int,
    active_seconds int,

    badges jsonb,

    pay_time_limit int,

    opportunity_score numeric,

    primary key (id, snapshot_time)
)
partition by range (snapshot_time);

/* Index creation */
create index idx_p2p_time on p2p_market_data(snapshot_time);

create index idx_p2p_pair on p2p_market_data(asset, fiat);

create index idx_p2p_merchant on p2p_market_data(merchant_id);

create index idx_p2p_price on p2p_market_data(price);

create index idx_p2p_trade_type on p2p_market_data(trade_type);

create index idx_p2p_market_time on p2p_market_data (asset, fiat, trade_type, snapshot_time);

create index idx_p2p_liquidity on p2p_market_data (tradable_quantity);

create index idx_p2p_merchant_time on p2p_market_data (merchant_id, snapshot_time);

create index idx_p2p_sell_market on p2p_market_data (asset, fiat, snapshot_time) where trade_type = 'SELL';

create index idx_p2p_buy_market on p2p_market_data (asset, fiat, snapshot_time) where trade_type = 'BUY';

/* Partition creation by  snapshot_time*/
SELECT public.create_parent(
    p_parent_table := 'public.p2p_market_data'::text,
    p_control := 'snapshot_time'::text,
    p_type := 'range'::text,
    p_interval := '1 day'::text
);