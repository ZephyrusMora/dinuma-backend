import os
import logging
from datetime import datetime, timezone
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Table, Column, Integer,
    String, MetaData, Boolean, func, Date, DateTime,
    PrimaryKeyConstraint, text
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
logger = logging.getLogger(__name__)

connection_uri = os.getenv("CONNECTION_URI") or os.getenv("DATABASE_URL")
if not connection_uri:
    raise RuntimeError("CONNECTION_URI or DATABASE_URL environment variable not set")

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



# DLB SCRAPER DATA)
dlb_draws = Table(
    "dlb_draws",
    metadata,
    Column("lottery_id", Integer, nullable=False),
    Column("draw_no", String, nullable=False),
    Column("date", String, nullable=False),
    Column("letter", String, nullable=True),
    Column("numbers", PG_ARRAY(Integer), nullable=False),
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

        conn.execute(stmt)
        logger.info("Inserted Jaya draw %s", draw_no_int)



# INSERT DLB DRAW
def insert_dlb_draw(draw_data: dict):
    lottery_id = draw_data.get("lottery_id")
    draw_no = draw_data.get("draw_no")   # FIXED KEY

    if lottery_id is None or draw_no is None:
        logger.warning("Missing lottery_id or draw_no in DLB insert")
        return

    numbers_list = draw_data.get("numbers") or []

    try:
        numbers = [int(n) for n in numbers_list]
    except Exception:
        logger.warning("Invalid numbers for DLB draw %s", draw_no)
        return

    with engine.begin() as conn:

        existing = conn.execute(
            select(dlb_draws.c.draw_no).where(
                (dlb_draws.c.draw_no == str(draw_no)) &
                (dlb_draws.c.lottery_id == lottery_id)
            )
        )

        if existing.first():
            return

        conn.execute(
            dlb_draws.insert().values(
                lottery_id=lottery_id,
                draw_no=draw_no,
                date=draw_data.get("date") or "",
                letter=draw_data.get("letter") or "",
                numbers=numbers,
                created_at=datetime.utcnow()
            )
        )


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


if __name__ == "__main__":
    init_db()
    print("Tables created.")