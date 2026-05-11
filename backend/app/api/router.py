from fastapi import APIRouter
from .v1.market import router as market_router
from .v1.strategy import router as strategy_router
from .v1.portfolio import router as portfolio_router
from .v1.analysis import router as analysis_router

api_router = APIRouter()

api_router.include_router(market_router, prefix="/v1/market", tags=["market"])
api_router.include_router(strategy_router, prefix="/v1/strategy", tags=["strategy"])
api_router.include_router(portfolio_router, prefix="/v1/portfolio", tags=["portfolio"])
api_router.include_router(analysis_router, prefix="/v1/analysis", tags=["analysis"])
