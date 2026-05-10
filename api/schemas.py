from typing import Optional, Literal
from pydantic import BaseModel, Field


Timeframe = Literal["1h", "12h", "24h"]
TradeType = Literal["BUY", "SELL"]


class MarketQuery(BaseModel):
    asset: str = Field(..., min_length=1, max_length=20)
    fiat: str = Field(..., min_length=1, max_length=20)
    tf: Timeframe = "1h"
    trade_type: TradeType = "BUY"


class OpportunityQuery(BaseModel):
    min_spread_pct: float = Field(default=0.3, ge=0)
    min_liquidity: float = Field(default=1000.0, ge=0)


class PremiumQuery(BaseModel):
    asset: str
    fiat: str
    spot_price_in_fiat: float = Field(..., gt=0)
    trade_type: TradeType = "BUY"
    tf: Timeframe = "1h"