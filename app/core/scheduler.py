import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from app.services.scraper import ScraperFactory
from app.services.db import insert_draw, get_max_draw_no, get_active_tokens, insert_dlb_draw
try:
    from app.services.firebase import send_draw_notification
except (ImportError, Exception):
    send_draw_notification = None
from app.services.dlb_scraper import ACTIVE_DLB_LOTTERIES, scrape_dlb_latest

logger = logging.getLogger(__name__)

LOTTERIES = [
    ("mahajana-sampatha", 6099),
    ("dhana-nidhanaya", 2161),
    ("govisetha", 4373),
    ("mega-power", 2479),
    ("nlb-jaya", 399),
]

# FALLBACK_LAST_DRAW_ID = 6099
SL_TZ = ZoneInfo("Asia/Colombo")
scheduler = BackgroundScheduler(timezone=SL_TZ)


def scheduled_scrape():
    """Run one scrape for each configured lottery."""
    for lottery_name, fallback_draw_number in LOTTERIES:
        try:
            max_db = get_max_draw_no(lottery_name)
            FALLBACK_LAST_DRAW_ID = fallback_draw_number
            next_id = (max_db + 1) if max_db is not None else (FALLBACK_LAST_DRAW_ID + 1)

            logger.info("[%s] Attempting to scrape draw %s", lottery_name, next_id)

            data = ScraperFactory.scrape("nlb", next_id, lottery_name=lottery_name)

            if data is None:
                logger.info("[%s] Draw %s not available yet", lottery_name, next_id)
                continue

            if not data.get("draw_no") or not data.get("numbers"):
                logger.warning(
                    "[%s] Incomplete data for draw %s, skipping: %s",
                    lottery_name,
                    next_id,
                    data,
                )
                continue

            insert_draw(data)
            logger.info("[%s] Scraped and inserted draw %s", lottery_name, data.get("draw_no"))

            # Send push notifications to subscribed users
            draw_no = data.get("draw_no")
            tokens = get_active_tokens(lottery_name)
            if tokens and send_draw_notification:
                send_draw_notification(lottery_name, draw_no, tokens)

        except Exception:
            logger.exception("scheduled_scrape failed for %s", lottery_name)

    # Refresh daily analytics cache once after scrape
    try:
        from app.services.analytics_service import refresh_analytics_cache
        refresh_analytics_cache(save_to_db=True)
        logger.info("Daily analytics cache refreshed after NLB scrape")
    except Exception:
        logger.exception("Failed refreshing analytics cache after NLB scrape")


def scheduled_dlb_scrape():
    """Run DLB scrape for all 9 active lotteries."""
    logger.info("=== Starting DLB Daily Scheduled Scrape ===")
    for lid, info in ACTIVE_DLB_LOTTERIES.items():
        try:
            draw = scrape_dlb_latest(lid)
            if draw and draw.get("draw_no") and draw.get("numbers"):
                inserted = insert_dlb_draw(draw)
                if inserted:
                    logger.info("[%s] Scraped and inserted DLB draw %s", info["name"], draw["draw_no"])
                    # Send push notifications if tokens exist
                    draw_no_int = int(draw["draw_no"])
                    tokens = get_active_tokens(info["slug"]) or get_active_tokens(info["name"])
                    if tokens and send_draw_notification:
                        send_draw_notification(info["name"], draw_no_int, tokens)
                else:
                    logger.info("[%s] DLB draw %s already up-to-date", info["name"], draw["draw_no"])
        except Exception:
            logger.exception("scheduled_dlb_scrape failed for %s", info["name"])

    # Refresh daily analytics cache once after DLB scrape
    try:
        from app.services.analytics_service import refresh_analytics_cache
        refresh_analytics_cache(save_to_db=True)
        logger.info("Daily analytics cache refreshed after DLB scrape")
    except Exception:
        logger.exception("Failed refreshing analytics cache after DLB scrape")


def start_scheduler():
    """Register the scrape job and start the background scheduler."""
    try:
        if not scheduler.get_job("mahajana_scrape"):
            scheduler.add_job(
                scheduled_scrape,
                "cron",
                hour=22,
                minute=0,
                timezone=SL_TZ,
                id='mahajana_scrape',
            )

        if not scheduler.get_job("dlb_scrape"):
            scheduler.add_job(
                scheduled_dlb_scrape,
                "cron",
                hour=22,
                minute=15,
                timezone=SL_TZ,
                id='dlb_scrape',
            )

        if not scheduler.running:
            scheduler.start()
            logger.info("Scheduler started — mahajana_scrape at 22:00, dlb_scrape at 22:15 SL time")

    except Exception:
        logger.exception("Failed to start scheduler")


def shutdown_scheduler():
    """Stop the background scheduler."""
    try:
        if scheduler.running:
            scheduler.shutdown()
            logger.info("Background scheduler stopped")
    except Exception:
        logger.exception("Failed to shutdown scheduler")