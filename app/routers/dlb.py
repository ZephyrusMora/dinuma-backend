from fastapi import APIRouter
from app.services.scraper import ScraperFactory
from app.services.db import insert_draw

router = APIRouter(prefix="/dlb", tags=["DLB"])


DLB_MAPPING = {
    "ada-kotipathi": 11,
    "sasiri": 13,
    "shanida": 1,
    "jayoda": 6,
    "kapruka": 12,
    "super-ball": 3,
    "supiri-dhana-sampatha": 17
}


@router.get("/scrape/{lottery_name}")
def scrape_and_store(lottery_name: str, limit: int = 5):

    lottery_id = DLB_MAPPING.get(lottery_name)
    if not lottery_id:
        return {"error": "Invalid lottery name"}

    data = ScraperFactory.scrape("dlb", lottery_id, lottery_name, limit=limit)

    inserted = 0

    for d in data:
        insert_draw(d)
        inserted += 1

    return {
        "message": "scrape complete",
        "inserted": inserted,
        "data": data
    }