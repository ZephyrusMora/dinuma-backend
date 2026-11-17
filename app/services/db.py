import os
import logging
from datetime import datetime, timezone
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Table, Column, Integer,
    String, MetaData, Boolean, func, Date, DateTime,
    PrimaryKeyConstraint, text, Text
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Look for .env in current and parent directories if not already loaded
env_file = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
if not os.path.exists(env_file):
    parent_env = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.env')
    if os.path.exists(parent_env):
        env_file = parent_env
load_dotenv(dotenv_path=env_file)
logger = logging.getLogger(__name__)

connection_uri = os.getenv("CONNECTION_URI") or os.getenv("DATABASE_URL")
if not connection_uri:
    raise RuntimeError("CONNECTION_URI or DATABASE_URL environment variable not set")

# Auto-convert plain postgresql:// to postgresql+psycopg2:// for SQLAlchemy compatibility
if connection_uri.startswith("postgresql://"):
    connection_uri = connection_uri.replace("postgresql://", "postgresql+psycopg2://", 1)

engine = create_engine(connection_uri)
metadata = MetaData()


# EXISTING TABLE (JAYA / NLB STYLE)
jaya_draws = Table(
    "jaya_draws",
    metadata,
    Column("lottery_name", String, nullable=False),
    Column("draw_no", Integer, nullable=False),
    Column("date", Date, nullable=False),
    Column("letter", String, nullable=False),
    Column("numbers", PG_ARRAY(Integer), nullable=False),
    Column("created_at", DateTime, default=datetime.utcnow),
    PrimaryKeyConstraint("lottery_name", "draw_no", name="jaya_draws_pk")
)



# DLB SCRAPER DATA
dlb_draws = Table(
    "dlb_draws",
    metadata,
    Column("lottery_id", Integer, nullable=False),
    Column("draw_no", String, nullable=False),
    Column("date", String, nullable=False),
    Column("letter", String, nullable=True),
    Column("numbers", PG_ARRAY(Integer), nullable=False),
    Column("lottery_name", String, nullable=True),
    Column("special_symbol", String, nullable=True),
    Column("special_number", Integer, nullable=True),
    Column("special_draw", String, nullable=True),
    Column("created_at", DateTime, default=datetime.utcnow),
    PrimaryKeyConstraint("lottery_id", "draw_no", name="dlb_draws_pk")
)



# FCM TOKENS 
fcm_tokens = Table(
    "fcm_tokens",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("user_id", String, nullable=True),
    Column("fcm_token", String, nullable=False, unique=True),
    Column("lottery_name", String, nullable=True),
    Column("is_active", Boolean, default=True),
    Column("created_at", String, default=lambda: str(datetime.now(timezone.utc))),
)


# DAILY PRECOMPUTED ANALYTICS CACHE
daily_analytics_cache = Table(
    "daily_analytics_cache",
    metadata,
    Column("lottery_id", String, primary_key=True),
    Column("category", String, nullable=False),
    Column("last_draw_no", String, nullable=True),
    Column("last_draw_date", String, nullable=True),
    Column("prediction_data", Text, nullable=False),
    Column("positional_data", Text, nullable=True),
    Column("backtest_data", Text, nullable=True),
    Column("updated_at", DateTime, default=datetime.utcnow),
)


# DB INIT
@contextmanager
def get_session():
    with engine.begin() as conn:
        yield conn


def init_db():
    metadata.create_all(engine)


# INSERT JAYA (NLB)
def insert_draw(draw_data: dict):
    draw_no = draw_data.get("draw_no")
    if draw_no is None:
        logger.warning("Skipping insert: draw_no is missing")
        return

    try:
        draw_no_int = int(draw_no)
    except (ValueError, TypeError):
        logger.warning("Skipping insert: invalid draw_no=%s", draw_no)
        return

    with engine.begin() as conn:

        existing = conn.execute(
            select(jaya_draws.c.draw_no).where(
                (jaya_draws.c.draw_no == draw_no_int) &
                (jaya_draws.c.lottery_name == draw_data.get("lottery_name"))
            )
        )

        if existing.first():
            logger.info("Draw %s already exists, skipping", draw_no_int)
            return

        numbers_list = draw_data.get("numbers") or []
        try:
            numbers = [int(n) for n in numbers_list]
        except Exception:
            logger.warning("Invalid numbers for draw %s", draw_no_int)
            return

        date_str = draw_data.get("date") or ""
        try:
            parsed_date = datetime.strptime(date_str, "%A %B %d, %Y").date()
        except Exception:
            parsed_date = datetime.utcnow().date()

        stmt = pg_insert(jaya_draws).values(
            lottery_name=draw_data.get("lottery_name"),
            draw_no=draw_no_int,
            date=parsed_date,
            letter=draw_data.get("letter") or "",
            numbers=numbers,
            created_at=datetime.utcnow(),
        )

        stmt = stmt.on_conflict_do_update(
            constraint="jaya_draws_pk",
            set_={
                "date": parsed_date,
                "letter": draw_data.get("letter"),
                "numbers": numbers,
            },
        )

        conn.execute(stmt)
        logger.info("Inserted Jaya draw %s", draw_no_int)



# INSERT DLB DRAW
def insert_dlb_draw(draw_data: dict) -> bool:
    lottery_id = draw_data.get("lottery_id")
    draw_no = draw_data.get("draw_no")

    if lottery_id is None or draw_no is None:
        logger.warning("Missing lottery_id or draw_no in DLB insert")
        return False

    numbers_list = draw_data.get("numbers") or []
    try:
        numbers = [int(n) for n in numbers_list]
    except Exception:
        logger.warning("Invalid numbers for DLB draw %s (lottery %s)", draw_no, lottery_id)
        return False

    draw_no_str = str(draw_no).strip()
    lottery_id_int = int(lottery_id)

    # Convert special_number if present
    sp_num = draw_data.get("special_number")
    if sp_num is not None:
        try:
            sp_num = int(sp_num)
        except (ValueError, TypeError):
            sp_num = None

    with engine.begin() as conn:
        existing = conn.execute(
            select(dlb_draws.c.draw_no).where(
                (dlb_draws.c.draw_no == draw_no_str) &
                (dlb_draws.c.lottery_id == lottery_id_int)
            )
        ).first()

        if existing:
            logger.info("DLB Draw %s for lottery %s already exists, skipping", draw_no_str, lottery_id_int)
            return False

        stmt = pg_insert(dlb_draws).values(
            lottery_id=lottery_id_int,
            draw_no=draw_no_str,
            date=str(draw_data.get("date") or "").strip(),
            letter=(draw_data.get("letter") or "").strip().upper(),
            numbers=numbers,
            lottery_name=draw_data.get("lottery_name") or "",
            special_symbol=draw_data.get("special_symbol") or "",
            special_number=sp_num,
            special_draw=draw_data.get("special_draw") or "",
            created_at=datetime.utcnow(),
        )

        stmt = stmt.on_conflict_do_update(
            constraint="dlb_draws_pk",
            set_={
                "date": str(draw_data.get("date") or "").strip(),
                "letter": (draw_data.get("letter") or "").strip().upper(),
                "numbers": numbers,
                "lottery_name": draw_data.get("lottery_name") or "",
                "special_symbol": draw_data.get("special_symbol") or "",
                "special_number": sp_num,
                "special_draw": draw_data.get("special_draw") or "",
            },
        )
        conn.execute(stmt)
        logger.info("Inserted DLB draw %s for lottery %s", draw_no_str, lottery_id_int)
        return True


def insert_dlb_draws_batch(draw_list: list) -> int:
    """Insert a list of DLB draw dictionaries, skipping duplicates."""
    inserted_count = 0
    for d in draw_list:
        try:
            if insert_dlb_draw(d):
                inserted_count += 1
        except Exception as e:
            logger.error("Failed to insert DLB draw %s: %s", d.get("draw_no"), e)
    return inserted_count


def get_max_dlb_draw_no(lottery_id: int) -> int | None:
    """Return highest integer draw_no for a given DLB lottery_id."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT MAX(CAST(draw_no AS INTEGER)) FROM public.dlb_draws WHERE lottery_id = :lid"),
            {"lid": int(lottery_id)}
        )
        return result.scalar()


def get_latest_dlb_draw(lottery_id: int) -> dict | None:
    """Return the most recent draw row for a given DLB lottery_id."""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT lottery_id, draw_no, date, letter, numbers, lottery_name, "
                "special_symbol, special_number, special_draw, created_at "
                "FROM public.dlb_draws WHERE lottery_id = :lid "
                "ORDER BY CAST(draw_no AS INTEGER) DESC LIMIT 1"
            ),
            {"lid": int(lottery_id)}
        ).mappings().first()
        return dict(result) if result else None


def get_max_draw_no(lottery_name: str):
    with engine.connect() as conn:
        result = conn.execute(
            select(func.max(jaya_draws.c.draw_no)).where(
                jaya_draws.c.lottery_name == lottery_name
            )
        )
        return result.scalar()


def delete_old_draws(months: int = 6):
    from datetime import timedelta
    from sqlalchemy import delete

    cutoff = datetime.utcnow().date() - timedelta(days=30 * months)

    with engine.begin() as conn:
        conn.execute(
            delete(jaya_draws).where(jaya_draws.c.date < cutoff)
        )


def upsert_fcm_token(fcm_token: str, user_id: str | None, lottery_name: str | None):
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO public.fcm_tokens (user_id, fcm_token, lottery_name, is_active, created_at)
                VALUES (:user_id, :fcm_token, :lottery_name, true, now())
                ON CONFLICT (fcm_token)
                DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    lottery_name = EXCLUDED.lottery_name,
                    is_active = true
            """),
            {"user_id": user_id, "fcm_token": fcm_token, "lottery_name": lottery_name},
        )


def get_active_tokens(lottery_name=None):
    with engine.connect() as conn:
        q = select(fcm_tokens.c.fcm_token).where(fcm_tokens.c.is_active == True)

        if lottery_name:
            q = q.where(
                (fcm_tokens.c.lottery_name == lottery_name) |
                (fcm_tokens.c.lottery_name == None)
            )

        return [r[0] for r in conn.execute(q).fetchall()]


def deactivate_token(token: str):
    with engine.begin() as conn:
        conn.execute(
            fcm_tokens.update()
            .where(fcm_tokens.c.fcm_token == token)
            .values(is_active=False)
        )


# ── ANALYTICS CACHE & DATA QUERIES ──

def upsert_analytics_cache(
    lottery_id: str,
    category: str,
    last_draw_no: str | None,
    last_draw_date: str | None,
    prediction_json: str,
    positional_json: str | None,
    backtest_json: str | None
):
    """Upsert daily precomputed analytics JSON in Postgres."""
    with engine.begin() as conn:
        stmt = pg_insert(daily_analytics_cache).values(
            lottery_id=lottery_id,
            category=category,
            last_draw_no=str(last_draw_no) if last_draw_no else None,
            last_draw_date=str(last_draw_date) if last_draw_date else None,
            prediction_data=prediction_json,
            positional_data=positional_json,
            backtest_data=backtest_json,
            updated_at=datetime.utcnow()
        )
        stmt = stmt.on_conflict_do_update(
            constraint="daily_analytics_cache_pkey",
            set_={
                "category": category,
                "last_draw_no": str(last_draw_no) if last_draw_no else None,
                "last_draw_date": str(last_draw_date) if last_draw_date else None,
                "prediction_data": prediction_json,
                "positional_data": positional_json,
                "backtest_data": backtest_json,
                "updated_at": datetime.utcnow()
            }
        )
        conn.execute(stmt)


def fetch_all_cached_analytics():
    """Fetch all rows from daily_analytics_cache."""
    with engine.connect() as conn:
        result = conn.execute(
            select(
                daily_analytics_cache.c.lottery_id,
                daily_analytics_cache.c.category,
                daily_analytics_cache.c.last_draw_no,
                daily_analytics_cache.c.last_draw_date,
                daily_analytics_cache.c.prediction_data,
                daily_analytics_cache.c.positional_data,
                daily_analytics_cache.c.backtest_data,
                daily_analytics_cache.c.updated_at
            )
        ).mappings().all()
        return [dict(r) for r in result]


def fetch_all_nlb_draws():
    """Fetch all rows from jaya_draws sorted by date ascending."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT lottery_name, draw_no, date, letter, numbers FROM public.jaya_draws ORDER BY date ASC, draw_no ASC")
        ).mappings().all()
        return [dict(r) for r in result]


def fetch_all_dlb_draws():
    """Fetch all rows from dlb_draws sorted by draw_no ascending."""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT lottery_id, draw_no, date, letter, numbers, lottery_name, special_symbol, special_number "
                "FROM public.dlb_draws "
                "ORDER BY CAST(draw_no AS INTEGER) ASC"
            )
        ).mappings().all()
        return [dict(r) for r in result]


if __name__ == "__main__":
    init_db()
    print("Tables created.")