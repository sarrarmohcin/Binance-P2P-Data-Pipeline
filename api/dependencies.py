from services.market import Market


market_engine = Market()


def get_market_engine() -> Market:
    return market_engine