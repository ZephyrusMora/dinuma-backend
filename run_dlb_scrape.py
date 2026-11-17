"""
Standalone script for Heroku Scheduler or manual execution to scrape DLB lottery draws.

Usage:
    # 1. Scrape latest draw for all 9 active DLB lotteries (daily scheduled scrape):
    python run_dlb_scrape.py

    # 2. Backfill historical pages (e.g. 5 pages per lottery):
    python run_dlb_scrape.py --backfill 5

    # 3. Scrape a single lottery:
    python run_dlb_scrape.py --lottery 11
    python run_dlb_scrape.py --lottery ada-kotipathi
"""
import argparse
import logging
import sys
import time

from app.services.dlb_scraper import (
    ACTIVE_DLB_LOTTERIES,
    ArchivedLotteryError,
    resolve_lottery_id,
    scrape_dlb_latest,
    scrape_dlb_historical,
    get_requests_session,
)
from app.services.db import (
    insert_dlb_draw,
    insert_dlb_draws_batch,
    get_max_dlb_draw_no,
    get_active_tokens,
)
try:
    from app.services.firebase import send_draw_notification
except (ImportError, Exception):
    send_draw_notification = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("run_dlb_scrape")


def scrape_latest_active_lotteries():
    """Scrape latest draw for all 9 active lotteries and store to database."""
    logger.info("=== Starting DLB Daily Scrape (9 active lotteries) ===")
    session = get_requests_session()
    total_new = 0

    for lid, info in ACTIVE_DLB_LOTTERIES.items():
        name = info["name"]
        slug = info["slug"]
        try:
            current_max = get_max_dlb_draw_no(lid)
            logger.info("[%s] Current max draw in DB: %s — fetching latest from DLB", name, current_max)

            draw = scrape_dlb_latest(lid, session=session)
            if not draw or not draw.get("draw_no") or not draw.get("numbers"):
                logger.warning("[%s] No valid draw returned from DLB", name)
                continue

            draw_no = draw["draw_no"]
            inserted = insert_dlb_draw(draw)

            if inserted:
                total_new += 1
                logger.info("[%s] Successfully inserted new draw %s (%s)", name, draw_no, draw["date"])
                try:
                    draw_no_int = int(draw_no)
                    tokens = get_active_tokens(slug) or get_active_tokens(name)
                    if tokens and send_draw_notification:
                        send_draw_notification(name, draw_no_int, tokens)
                except Exception as ne:
                    logger.warning("[%s] Failed to send notification: %s", name, ne)
            else:
                logger.info("[%s] Draw %s is already up-to-date in DB", name, draw_no)

        except Exception as e:
            logger.error("[%s] Scrape failed: %s", name, e, exc_info=True)

        time.sleep(0.4)

    logger.info("=== DLB Daily Scrape Finished: %s new draws inserted ===", total_new)
    return total_new


def backfill_lotteries(max_pages: int, target_lottery: int | str | None = None):
    """Backfill historical draws for active lotteries."""
    logger.info("=== Starting DLB Historical Backfill (pages: %s) ===", max_pages)
    session = get_requests_session()

    if target_lottery is not None:
        targets = [resolve_lottery_id(target_lottery)]
    else:
        targets = list(ACTIVE_DLB_LOTTERIES.keys())

    total_inserted = 0
    for lid in targets:
        name = ACTIVE_DLB_LOTTERIES[lid]["name"]
        logger.info("[%s] Backfilling up to %s pages...", name, max_pages)
        try:
            draws = scrape_dlb_historical(lid, max_pages=max_pages, delay=0.5, session=session)
            logger.info("[%s] Scraped %s total draws. Saving to database...", name, len(draws))
            inserted = insert_dlb_draws_batch(draws)
            total_inserted += inserted
            logger.info("[%s] Ingestion complete. %s new draws inserted.", name, inserted)
        except Exception as e:
            logger.error("[%s] Backfill failed: %s", name, e, exc_info=True)

    logger.info("=== Historical Backfill Finished: %s total new draws inserted ===", total_inserted)
    return total_inserted


def main():
    parser = argparse.ArgumentParser(description="DLB Lottery Data Pipeline Runner")
    parser.add_argument(
        "--lottery",
        type=str,
        default=None,
        help="Specify single lottery ID or slug (e.g. 11 or ada-kotipathi)"
    )
    parser.add_argument(
        "--backfill",
        type=int,
        default=None,
        help="Number of historical pages to backfill (e.g. --backfill 5)"
    )

    args = parser.parse_args()

    if args.backfill:
        backfill_lotteries(max_pages=args.backfill, target_lottery=args.lottery)
    elif args.lottery:
        try:
            lid = resolve_lottery_id(args.lottery)
            info = ACTIVE_DLB_LOTTERIES[lid]
            logger.info("Fetching latest draw for %s (ID %s)...", info["name"], lid)
            draw = scrape_dlb_latest(lid)
            if draw:
                inserted = insert_dlb_draw(draw)
                logger.info("Draw %s: %s (New: %s)", draw["draw_no"], draw, inserted)
            else:
                logger.warning("No draw returned.")
        except ArchivedLotteryError as ae:
            logger.error("Cannot scrape archived lottery: %s", ae)
            sys.exit(1)
        except Exception as e:
            logger.error("Scrape failed: %s", e)
            sys.exit(1)
    else:
        scrape_latest_active_lotteries()


if __name__ == "__main__":
    main()
