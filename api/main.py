from fastapi import FastAPI
from routers.analytics import router as analytics_router


app = FastAPI(
    title="Binance P2P Analytics API",
    version="1.0.0"
)


app.include_router(analytics_router)


@app.get("/")
def root():
    return {
        "message": "Binance P2P Analytics API"
    }