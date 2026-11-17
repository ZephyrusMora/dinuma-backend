"""
Daily Precomputed Analytics Service for Dinuma Heroku Backend.
Handles in-memory caching and persistent Postgres storage to serve instant analytics
with zero CPU overhead during user requests.
"""
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import numpy as np

from app.constants.lottery_config import LOTTERIES, DLB_ID_TO_SLUG
from app.services.prediction_engine import PredictionEngine
from app.services.db import (
    fetch_all_nlb_draws,
    fetch_all_dlb_draws,
    upsert_analytics_cache,
    fetch_all_cached_analytics
)

logger = logging.getLogger(__name__)

# In-memory fast stores
_DRAWS_STORE: Dict[str, List[Dict[str, Any]]] = {}
_PRECOMPUTED_CATALOG: Dict[str, List[Dict[str, Any]]] = {"NLB": [], "DLB": []}
_PRECOMPUTED_PREDICTIONS: Dict[str, Dict[str, Any]] = {}
_PRECOMPUTED_POSITIONAL: Dict[str, Dict[str, Any]] = {}
_PRECOMPUTED_BACKTESTS: Dict[str, Dict[str, Any]] = {}


def _json_serializer(obj):
    """Custom serializer for numpy types and dates."""
    if isinstance(obj, (np.integer, int)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return float(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (datetime,)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def load_draws_from_db():
    """Load and normalize all historical draws from PostgreSQL into memory."""
    global _DRAWS_STORE
    logger.info("Loading lottery draws from PostgreSQL...")

    draws_map: Dict[str, List[Dict[str, Any]]] = {lid: [] for lid in LOTTERIES}

    # 1. NLB from jaya_draws
    try:
        nlb_rows = fetch_all_nlb_draws()
        for r in nlb_rows:
            lname = r.get("lottery_name")
            if lname not in LOTTERIES:
                continue

            numbers = r.get("numbers") or []
            try:
                numbers = [int(n) for n in numbers]
            except Exception:
                continue

            special_num = None
            main_numbers = numbers
            if lname == "mega-power":
                if len(numbers) >= 5:
                    special_num = numbers[0]
                    main_numbers = numbers[1:]

            entry = {
                "draw_no": r.get("draw_no"),
                "date": str(r.get("date")),
                "letter": (r.get("letter") or "").strip().upper(),
                "symbol": "",
                "numbers": main_numbers,
                "special_number": special_num
            }
            draws_map[lname].append(entry)
        logger.info("Loaded %d NLB draws across %d lotteries", len(nlb_rows), len([k for k, v in LOTTERIES.items() if v["category"] == "NLB"]))
    except Exception as e:
        logger.error("Failed loading NLB draws: %s", e)

    # 2. DLB from dlb_draws
    try:
        dlb_rows = fetch_all_dlb_draws()
        for r in dlb_rows:
            lid_num = r.get("lottery_id")
            slug = DLB_ID_TO_SLUG.get(lid_num)
            if not slug or slug not in LOTTERIES:
                continue

            numbers = r.get("numbers") or []
            try:
                numbers = [int(n) for n in numbers]
            except Exception:
                continue

            entry = {
                "draw_no": r.get("draw_no"),
                "date": str(r.get("date")),
                "letter": (r.get("letter") or "").strip().upper(),
                "symbol": (r.get("special_symbol") or "").strip(),
                "numbers": numbers,
                "special_number": r.get("special_number")
            }
            draws_map[slug].append(entry)
        logger.info("Loaded %d DLB draws across %d active lotteries", len(dlb_rows), len(DLB_ID_TO_SLUG))
    except Exception as e:
        logger.error("Failed loading DLB draws: %s", e)

    _DRAWS_STORE = draws_map
    _build_catalog()


def _build_catalog():
    """Build summary catalog for all lotteries."""
    global _PRECOMPUTED_CATALOG
    cat_nlb = []
    cat_dlb = []

    for lid, cfg in LOTTERIES.items():
        draws = _DRAWS_STORE.get(lid, [])
        latest = draws[-1] if draws else None
        earliest = draws[0] if draws else None

        summary = {
            "id": lid,
            "name": cfg["name"],
            "category": cfg["category"],
            "type": cfg["type"],
            "pool": cfg["pool"],
            "count_per_draw": cfg["count_per_draw"],
            "has_letter": cfg["has_letter"],
            "has_symbol": cfg["has_symbol"],
            "has_special_num": cfg["has_special_num"],
            "special_pool": cfg.get("special_pool"),
            "description": cfg["description"],
            "total_draws": len(draws),
            "latest_draw": latest,
            "earliest_date": earliest["date"] if earliest else None,
            "latest_date": latest["date"] if latest else None
        }

        if cfg["category"] == "NLB":
            cat_nlb.append(summary)
        else:
            cat_dlb.append(summary)

    _PRECOMPUTED_CATALOG = {
        "NLB": cat_nlb,
        "DLB": cat_dlb
    }


def refresh_analytics_cache(default_window: int = 100, save_to_db: bool = True):
    """
    Recalculate complete statistical forecasts, candidate pools,
    positional Markov matrices, and backtests for all lotteries.
    Takes ~0.05 seconds total.
    """
    global _PRECOMPUTED_PREDICTIONS, _PRECOMPUTED_POSITIONAL, _PRECOMPUTED_BACKTESTS
    logger.info("=== Refreshing Daily Analytics Cache ===")

    load_draws_from_db()
    engine = PredictionEngine()

    new_pred = {}
    new_pos = {}
    new_bt = {}

    for lid, cfg in LOTTERIES.items():
        draws = _DRAWS_STORE.get(lid, [])
        if not draws:
            continue

        try:
            # 1. Prediction & Candidate Pool
            pred_data = engine.analyze_and_predict(lid, draws, window_size=default_window)
            new_pred[lid] = pred_data

            # 2. Positional Matrix (Digit lotteries)
            pos_data = None
            if cfg["type"] == "digit":
                pos_data = engine.get_positional_analysis(lid, draws, window_size=default_window)
                new_pos[lid] = pos_data

            # 3. Walk-Forward Backtesting (30 draws)
            bt_data = None
            if len(draws) >= 40:
                bt_data = engine.run_backtest(lid, draws, test_draws=30, window_size=default_window)
                new_bt[lid] = bt_data

            # 4. Save to Postgres
            if save_to_db:
                latest_draw = draws[-1]
                pred_json = json.dumps(pred_data, default=_json_serializer)
                pos_json = json.dumps(pos_data, default=_json_serializer) if pos_data else None
                bt_json = json.dumps(bt_data, default=_json_serializer) if bt_data else None

                upsert_analytics_cache(
                    lottery_id=lid,
                    category=cfg["category"],
                    last_draw_no=str(latest_draw.get("draw_no")),
                    last_draw_date=str(latest_draw.get("date")),
                    prediction_json=pred_json,
                    positional_json=pos_json,
                    backtest_json=bt_json
                )
        except Exception as e:
            logger.error("Error calculating analytics for %s: %s", lid, e)

    _PRECOMPUTED_PREDICTIONS = new_pred
    _PRECOMPUTED_POSITIONAL = new_pos
    _PRECOMPUTED_BACKTESTS = new_bt
    logger.info("=== Analytics Cache Successfully Refreshed (%d lotteries) ===", len(new_pred))


def init_analytics_cache():
    """
    Called on FastAPI startup.
    Loads existing precomputed analytics from Postgres in ~10ms.
    If database cache is empty, triggers a fresh precomputation.
    """
    global _PRECOMPUTED_PREDICTIONS, _PRECOMPUTED_POSITIONAL, _PRECOMPUTED_BACKTESTS
    logger.info("Initializing analytics cache on startup...")

    load_draws_from_db()

    try:
        cached_rows = fetch_all_cached_analytics()
        if cached_rows:
            logger.info("Found %d precomputed lottery records in Postgres cache. Hydrating memory...", len(cached_rows))
            for r in cached_rows:
                lid = r["lottery_id"]
                if r.get("prediction_data"):
                    _PRECOMPUTED_PREDICTIONS[lid] = json.loads(r["prediction_data"])
                if r.get("positional_data"):
                    _PRECOMPUTED_POSITIONAL[lid] = json.loads(r["positional_data"])
                if r.get("backtest_data"):
                    _PRECOMPUTED_BACKTESTS[lid] = json.loads(r["backtest_data"])
            logger.info("Startup cache hydration complete!")
            return
    except Exception as e:
        logger.warning("Failed loading analytics cache from Postgres: %s", e)

    logger.info("Postgres cache empty or unreadable. Running precomputation now...")
    refresh_analytics_cache(default_window=100, save_to_db=True)


# ── GETTER METHODS FOR ENDPOINTS (Sub-millisecond latency) ──

def get_lottery_catalog() -> Dict[str, List[Dict[str, Any]]]:
    return _PRECOMPUTED_CATALOG


def get_cached_prediction(lottery_id: str, window_size: Optional[int] = None) -> Optional[Dict[str, Any]]:
    # If standard window (or not specified), return precomputed cache immediately
    if (window_size is None or window_size == 100) and lottery_id in _PRECOMPUTED_PREDICTIONS:
        return _PRECOMPUTED_PREDICTIONS[lottery_id]

    # If custom window requested, compute on demand
    draws = _DRAWS_STORE.get(lottery_id, [])
    if not draws:
        return None
    return PredictionEngine.analyze_and_predict(lottery_id, draws, window_size=window_size)


def get_cached_positional(lottery_id: str, window_size: Optional[int] = None) -> Optional[Dict[str, Any]]:
    if (window_size is None or window_size == 100) and lottery_id in _PRECOMPUTED_POSITIONAL:
        return _PRECOMPUTED_POSITIONAL[lottery_id]

    draws = _DRAWS_STORE.get(lottery_id, [])
    if not draws:
        return None
    return PredictionEngine.get_positional_analysis(lottery_id, draws, window_size=window_size)


def get_cached_backtest(lottery_id: str, test_draws: int = 30, window_size: int = 100) -> Optional[Dict[str, Any]]:
    if test_draws == 30 and window_size == 100 and lottery_id in _PRECOMPUTED_BACKTESTS:
        return _PRECOMPUTED_BACKTESTS[lottery_id]

    draws = _DRAWS_STORE.get(lottery_id, [])
    if not draws:
        return None
    return PredictionEngine.run_backtest(lottery_id, draws, test_draws=test_draws, window_size=window_size)


def validate_user_ticket(lottery_id: str, numbers: List[int]) -> Dict[str, Any]:
    draws = _DRAWS_STORE.get(lottery_id, [])
    return PredictionEngine.validate_ticket(lottery_id, numbers, draws)
