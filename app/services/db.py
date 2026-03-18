import os
import logging
from datetime import datetime, timezone
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Table, Column, Integer,
    String, MetaData, Boolean, func, Date, DateTime, PrimaryKeyConstraint
)
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import select
from sqlmodel import Session

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
logger = logging.getLogger(__name__)

connection_uri = os.getenv("CONNECTION_URI") or os.getenv("DATABASE_URL")
if not connection_uri:
    raise RuntimeError("CONNECTION_URI or DATABASE_URL environment variable not set")

engine = create_engine(connection_uri)
metadata = MetaData()

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

@contextmanager
def get_session():
    """Provide a SQLModel session for webhook and other services."""
    with Session(engine) as session:
        yield session

def init_db():
    """Create the tables defined in metadata if they don't exist."""
    metadata.create_all(engine)


def insert_draw(draw_data: dict):
    """Validate and insert a single draw record, skipping duplicates."""
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
        except (ValueError, TypeError):
            logger.warning("Skipping insert: invalid numbers for draw %s", draw_no_int)
            return

        date_str = draw_data.get("date") or ""
        try:
            parsed_date = datetime.strptime(date_str, "%A %B %d, %Y").date()
        except Exception:
            logger.warning("Invalid date format: %s", date_str)
            return

        stmt = jaya_draws.insert().values(
            lottery_name=draw_data.get("lottery_name") or "unknown",
            draw_no=draw_no_int,
            date=parsed_date,
            letter=draw_data.get("letter") or "",
            numbers=numbers,
            created_at=datetime.utcnow(),
        )

        try:
            conn.execute(stmt)
            logger.info("Inserted draw %s", draw_no_int)
        except IntegrityError:
            logger.exception("Failed to insert draw %s", draw_no_int)


def get_max_draw_no(lottery_name: str):
    """Return the maximum draw_no for a specific lottery, or None if empty."""
    with engine.connect() as conn:
        try:
            result = conn.execute(
                select(func.max(jaya_draws.c.draw_no)).where(
                    jaya_draws.c.lottery_name == lottery_name
                )
            )
            max_val = result.scalar()
            return int(max_val) if max_val is not None else None
        except Exception:
            logger.exception("Failed to get max draw_no for %s", lottery_name)
            return None


def delete_old_draws(months: int = 6):
    """Delete draws older than `months` months."""
    from datetime import timedelta
    from sqlalchemy import delete

    cutoff_date = datetime.utcnow().date() - timedelta(days=30 * months)
    with engine.begin() as conn:
        stmt = delete(jaya_draws).where(jaya_draws.c.date < cutoff_date)
        result = conn.execute(stmt)
        logger.info("Deleted %s old rows.", result.rowcount)


def upsert_fcm_token(token: str, user_id, lottery_name=None):
    """Insert or reactivate an FCM token. user_id may be None for anonymous users."""
    with engine.begin() as conn:
        existing = conn.execute(
            select(fcm_tokens.c.id).where(fcm_tokens.c.fcm_token == token)
        ).first()
        if existing:
            conn.execute(
                fcm_tokens.update()
                .where(fcm_tokens.c.fcm_token == token)
                .values(is_active=True, user_id=user_id)
            )
        else:
            conn.execute(fcm_tokens.insert().values(
                user_id=user_id,
                fcm_token=token,
                lottery_name=lottery_name,
                is_active=True,
                created_at=str(datetime.now(timezone.utc)),
            ))


def get_active_tokens(lottery_name=None):
    """Return all active FCM tokens, optionally filtered by lottery subscription."""
    with engine.connect() as conn:
        q = select(fcm_tokens.c.fcm_token).where(fcm_tokens.c.is_active == True)
        if lottery_name:
            q = q.where(
                (fcm_tokens.c.lottery_name == lottery_name) |
                (fcm_tokens.c.lottery_name == None)
            )
        rows = conn.execute(q).fetchall()
        return [r[0] for r in rows]


def deactivate_token(token: str):
    """Mark a token as inactive (e.g. after FCM reports it as invalid)."""
    with engine.begin() as conn:
        conn.execute(
            fcm_tokens.update()
            .where(fcm_tokens.c.fcm_token == token)
            .values(is_active=False)
        )


if __name__ == '__main__':
    init_db()
    print("Tables created.")