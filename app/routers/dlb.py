from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import logging

from app.services.dlb_scraper import (
    ACTIVE_DLB_LOTTERIES,
    ArchivedLotteryError,
    resolve_lottery_id,
    scrape_dlb_latest,
    scrape_dlb_page,
    scrape_all_active_dlb_latest,
    scrape_dlb_historical,
)
from app.services.db import (
    insert_dlb_draw,
    insert_dlb_draws_batch,
    get_max_dlb_draw_no,
    get_latest_dlb_draw,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dlb", tags=["DLB"])


class BackfillRequest(BaseModel):
    lottery_id: int | str
    max_pages: int = 5
    delay: float = 0.5


@router.get("/lotteries")
def list_active_lotteries():
    """Return all 9 active DLB lotteries."""
    return {
        "status": "success",
        "count": len(ACTIVE_DLB_LOTTERIES),
        "lotteries": list(ACTIVE_DLB_LOTTERIES.values())
    }


@router.get("/scrape/latest")
def scrape_all_latest():
    """Scrape the latest draw for all 9 active DLB lotteries and store to database."""
    results = scrape_all_active_dlb_latest()
    inserted_count = 0
    details = {}

    for slug, draw in results.items():
        if draw:
            inserted = insert_dlb_draw(draw)
            if inserted:
                inserted_count += 1
            details[slug] = {
                "draw_no": draw["draw_no"],
                "date": draw["date"],
                "inserted": inserted
            }
        else:
            details[slug] = None

    return {
        "status": "success",
        "lotteries_scraped": len(results),
        "new_draws_inserted": inserted_count,
        "results": details
    }


@router.get("/scrape/{lottery_id}/latest")
def scrape_single_latest(lottery_id: str):
    """Scrape latest draw for a single lottery and store it in database."""
    try:
        lid = resolve_lottery_id(lottery_id)
    except ArchivedLotteryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    draw = scrape_dlb_latest(lid)
    if not draw:
        raise HTTPException(status_code=502, detail="Failed to fetch latest draw from DLB")

    inserted = insert_dlb_draw(draw)
    return {
        "status": "success",
        "inserted": inserted,
        "draw": draw
    }


@router.get("/scrape/{lottery_id}/page/{page_id}")
def scrape_page(lottery_id: str, page_id: int):
    """Scrape a specific results page (1-based) for a lottery."""
    try:
        lid = resolve_lottery_id(lottery_id)
    except ArchivedLotteryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    draws = scrape_dlb_page(lid, page_id=page_id)
    inserted = insert_dlb_draws_batch(draws)

    return {
        "status": "success",
        "page_id": page_id,
        "draws_found": len(draws),
        "new_draws_inserted": inserted,
        "draws": draws
    }


@router.post("/scrape/backfill")
def backfill_lottery(req: BackfillRequest):
    """Backfill historical draws for a lottery up to max_pages."""
    try:
        lid = resolve_lottery_id(req.lottery_id)
    except ArchivedLotteryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    draws = scrape_dlb_historical(lid, max_pages=req.max_pages, delay=req.delay)
    inserted = insert_dlb_draws_batch(draws)

    return {
        "status": "success",
        "lottery_id": lid,
        "total_scraped": len(draws),
        "new_inserted": inserted
    }


@router.get("/draws/{lottery_id}/latest")
def get_latest_draw(lottery_id: str):
    """Get the latest draw record stored in Supabase DB for a given lottery."""
    try:
        lid = resolve_lottery_id(lottery_id)
    except ArchivedLotteryError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    draw = get_latest_dlb_draw(lid)
    max_no = get_max_dlb_draw_no(lid)

    if not draw:
        raise HTTPException(status_code=404, detail="No draws found in database for this lottery")

    return {
        "lottery_id": lid,
        "max_draw_no": max_no,
        "latest_draw": draw
    }
