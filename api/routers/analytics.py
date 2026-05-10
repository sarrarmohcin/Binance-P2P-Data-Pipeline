from fastapi import APIRouter, Depends, HTTPException
from services.market import Market
from dependencies import get_market_engine
from schemas import MarketQuery, OpportunityQuery, PremiumQuery

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/snapshot")
def market_snapshot(
    asset: str,
    fiat: str,
    tf: str = "1h",
    market: Market = Depends(get_market_engine)
):
    result = market.market_snapshot(asset, fiat, tf)
    if not result:
        raise HTTPException(status_code=404, detail="No data found")
    return result


@router.get("/spread")
def spread(
    asset: str,
    fiat: str,
    tf: str = "1h",
    market: Market = Depends(get_market_engine)
):
    result = market.spread(asset, fiat, tf)
    if not result:
        raise HTTPException(status_code=404, detail="No spread data")
    return result


@router.get("/spread-all-windows")
def spread_all_windows(
    asset: str,
    fiat: str,
    market: Market = Depends(get_market_engine)
):
    return market.spread_all_windows(asset, fiat)


@router.get("/volatility")
def volatility_analysis(
    asset: str,
    fiat: str,
    trade_type: str = "BUY",
    market: Market = Depends(get_market_engine)
):
    return market.volatility_analysis(asset, fiat, trade_type)


@router.get("/momentum")
def momentum(
    asset: str,
    fiat: str,
    trade_type: str = "BUY",
    market: Market = Depends(get_market_engine)
):
    return market.price_momentum(asset, fiat, trade_type)


@router.get("/leaderboard")
def leaderboard(
    market: Market = Depends(get_market_engine)
):
    try:
        df = market.leaderboard()


        return df.to_dict(orient="records")

    except Exception as e:
        print("LEADERBOARD ERROR:", str(e))
        return {
            "error": str(e)
        }