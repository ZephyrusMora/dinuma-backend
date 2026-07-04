from fastapi import APIRouter
from typing import Optional

from app.services.scraper import ScraperFactory
from app.services.db import insert_draw

router = APIRouter(prefix="/mahajana", tags=["Mahajana Sampatha"])


@router.get("/scrape/{draw_id}")
def scrape_and_insert(draw_id: int, lottery_name: Optional[str] = "mahajana-sampatha"):
    """Scrape a specific draw by ID and insert the result into the database."""
    draw_data = ScraperFactory.scrape("nlb", draw_id, lottery_name=lottery_name)

    if not draw_data:
        return {"error": "Scraping failed"}

    insert_draw(draw_data)

    return {
        "message": f"Draw {draw_id} scraped and inserted successfully",
        "draw": draw_data,
    }
