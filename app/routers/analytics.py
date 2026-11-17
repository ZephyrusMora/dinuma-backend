"""
Analytics & Prediction Router for Dinuma Backend.
Provides high-performance, precomputed lottery analytics, candidate pools,
positional matrices, and backtest results.
"""
from fastapi import APIRouter, HTTPException, Query, Response, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

from app.services import analytics_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Analytics & Predictions"])


class TicketValidationRequest(BaseModel):
    lottery_id: str
    numbers: List[int]


@router.get("/lotteries")
@router.get("/api/lotteries")
def list_lotteries(response: Response):
    """
    Return all supported lotteries categorized by board (NLB and DLB),
    with metadata, draw counts, and latest draw numbers.
    """
    response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=86400"
    return analytics_service.get_lottery_catalog()


@router.get("/predict/{lottery_id}")
@router.get("/api/predict/{lottery_id}")
def get_prediction(
    lottery_id: str,
    response: Response,
    window: Optional[int] = Query(100, description="Analysis window size (past draws)")
):
    """
    Return top-10 candidate pool (Core Bankers, Velocity, Overdue Poisson Hazard),
    bonus letter/zodiac/powerball predictions, and recommended combinations.
    """
    result = analytics_service.get_cached_prediction(lottery_id, window_size=window)
    if not result:
        raise HTTPException(status_code=404, detail=f"Lottery '{lottery_id}' not found or has no draws.")
    
    response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=86400"
    return result


@router.get("/positional/{lottery_id}")
@router.get("/api/positional/{lottery_id}")
def get_positional_analysis(
    lottery_id: str,
    response: Response,
    window: Optional[int] = Query(100, description="Analysis window size")
):
    """
    Return machine-specific positional column frequency, Chi-Square uniformity tests,
    and 1st-order column Markov transition probabilities (for digit lotteries).
    """
    try:
        result = analytics_service.get_cached_positional(lottery_id, window_size=window)
        if not result:
            raise HTTPException(status_code=404, detail=f"Lottery '{lottery_id}' not found or not a digit lottery.")
        response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=86400"
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/backtest/{lottery_id}")
@router.get("/api/backtest/{lottery_id}")
def get_backtest(
    lottery_id: str,
    response: Response,
    test_draws: int = Query(30, description="Number of past draws to backtest"),
    window: int = Query(100, description="Rolling window size")
):
    """
    Return sequential walk-forward backtest results comparing model candidate pools
    vs actual historical draw outcomes.
    """
    try:
        result = analytics_service.get_cached_backtest(lottery_id, test_draws=test_draws, window_size=window)
        if not result:
            raise HTTPException(status_code=404, detail=f"Lottery '{lottery_id}' has insufficient draws for backtesting.")
        response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=86400"
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/validate-ticket")
@router.post("/api/validate-ticket")
def validate_ticket(payload: TicketValidationRequest):
    """
    Evaluate user ticket combination against sum envelopes, odd/even parity filters,
    and machine column biases.
    """
    try:
        return analytics_service.validate_user_ticket(payload.lottery_id, payload.numbers)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/refresh")
@router.post("/api/refresh-analytics")
def trigger_refresh(background_tasks: BackgroundTasks):
    """
    Trigger immediate background recalculation and cache update for all lotteries.
    """
    background_tasks.add_task(analytics_service.refresh_analytics_cache, 100, True)
    return {"status": "accepted", "message": "Daily analytics recalculation running in background."}
