import logging
from fastapi import APIRouter, Request, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from app.services.db import get_session
from app.services.notification_service import send_win_notification
from app.constants.prizes import LOTTERY_PRIZES
from app.services.lottery_checker import check_ticket_for_lottery
from sqlmodel import Session, text

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/webhook",
    tags=["webhook"],
)


class RegisterFcmTokenRequest(BaseModel):
    user_id: int = Field(..., gt=0)
    fcm_token: str = Field(..., min_length=10)


@router.post("/register-fcm-token")
def register_fcm_token(payload: RegisterFcmTokenRequest):
    """Persist or update the device FCM token for a user."""
    with get_session() as session:
        exists_query = text("SELECT id FROM public.users WHERE id = :user_id")
        existing_user = session.execute(exists_query, {"user_id": payload.user_id}).fetchone()

        if not existing_user:
            raise HTTPException(status_code=404, detail="User not found")

        update_query = text(
            """
            UPDATE public.users
            SET fcm_token = :fcm_token
            WHERE id = :user_id
            """
        )
        session.execute(
            update_query,
            {"user_id": payload.user_id, "fcm_token": payload.fcm_token},
        )
        session.commit()

    return {"status": "ok", "message": "FCM token saved"}


def process_new_draw(payload: dict):
    record = payload.get("record", {})
    if not record:
        logger.warning("Webhook payload missing 'record' field")
        return

    lottery_name = record.get("lottery_name")
    draw_no = record.get("draw_no")
    draw_numbers = record.get("numbers", [])
    
    # Ensure draw_numbers is a list
    if draw_numbers is None:
        draw_numbers = []
    elif isinstance(draw_numbers, str):
        if draw_numbers.startswith('{') and draw_numbers.endswith('}'):
            draw_numbers = [int(n.strip()) for n in draw_numbers[1:-1].split(',') if n.strip().isdigit()]
        else:
            # Fallback in case it's a JSON string
            import json
            try:
                draw_numbers = json.loads(draw_numbers)
            except:
                draw_numbers = []
    
    if not isinstance(draw_numbers, list):
        draw_numbers = []

    draw_letter = record.get("letter")
    draw_special_component = record.get("special_component") or record.get("power_number") or record.get("power")
    if draw_special_component is not None:
        try:
            draw_special_component = int(draw_special_component)
        except (ValueError, TypeError):
            logger.warning(f"Invalid draw special component for {lottery_name} {draw_no}: {draw_special_component}")
            draw_special_component = None

    if not lottery_name or draw_no is None:
        logger.error(f"Incomplete draw record: {record}")
        return
        
    # Cast to string to avoid Postgres "operator does not exist: text = integer" error
    draw_no = str(draw_no)

    logger.info(f"Processing new draw: {lottery_name} #{draw_no}")

    normalized_lottery_key = str(lottery_name).upper().replace('-', '_')
    prize_tiers = LOTTERY_PRIZES.get(normalized_lottery_key)
    if not prize_tiers:
        logger.info(f"No prize tiers found for lottery type: {lottery_name} (normalized as {normalized_lottery_key})")
        return
    
    lottery_names = ["govisetha", "mahajana-sampatha", "nlb-jaya", "dhana-nidhanaya", "mega-power"]

    LOTTERY_TYPE_MAP = {
        "govisetha": "GOVISETHA",
        "dhana-nidhanaya": "DHANA_NIDHANAYA",
        "dhana_nidhanaya": "DHANA_NIDHANAYA",
        "mahajana-sampatha": "MAHAJANA_SAMPATHA",
        "mahajana_sampatha": "MAHAJANA_SAMPATHA",
        "mega-power": "MEGA_POWER",
        "mega_power": "MEGA_POWER",
    }

    normalized_name = str(lottery_name).strip().lower().replace(" ", "_")
    if normalized_name not in LOTTERY_TYPE_MAP:
        logger.info(f"No ticket processing handler yet for lottery type: {lottery_name}")
        return

    db_lottery_type = LOTTERY_TYPE_MAP[normalized_name]

    with get_session() as session:
        lottery_key = str(lottery_name).lower()
        if lottery_key in lottery_names:
            try:
                # Normalize the lottery type to match DB values (replace hyphen with underscore, uppercase)
                lottery_type = lottery_key.replace('-', '_').upper()

                query = text("""
                    SELECT id, user_id, scanned_numbers, scanned_letter, scanned_special_component
                    FROM public.tickets
                    WHERE lottery_type = :lottery_type
                      AND draw_number = :draw_no
                      AND status = 'PENDING'
                """)
                tickets = session.execute(query, {"lottery_type": lottery_type, "draw_no": draw_no}).fetchall()

                logger.info(f"Found {len(tickets)} pending {lottery_key} tickets for draw {draw_no}")

                for ticket in tickets:
                    ticket_id, user_id, scanned_nums, scanned_letter, scanned_special_component = ticket
                    t_nums = scanned_nums if isinstance(scanned_nums, list) else []
                    ticket_special_component = None
                    if scanned_special_component is not None:
                        try:
                            ticket_special_component = int(scanned_special_component)
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid scanned special component for ticket {ticket_id}: {scanned_special_component}")

                    result = check_lottery_ticket(
                        ticket_numbers=t_nums,
                        ticket_letter=scanned_letter,
                        draw_numbers=draw_numbers,
                        draw_letter=draw_letter,
                        prize_tiers=prize_tiers,
                        special_component=draw_special_component,
                        ticket_special_component=ticket_special_component
                    )

                    new_status = 'WIN' if result["is_winner"] else 'NO_WIN'
                    win_amt = result["win_amount"]

                    update_query = text("""
                        UPDATE public.tickets
                        SET status = :status, win_amount = :win_amt
                        WHERE id = :id
                    """)
                    session.execute(update_query, {"status": new_status, "win_amt": win_amt, "id": ticket_id})

                    if result["is_winner"]:
                        logger.info(f"Ticket {ticket_id} WON Rs {win_amt}")
                        user_query = text("SELECT fcm_token FROM public.fcm_tokens WHERE user_id = :user_id AND is_active = true")
                        user_record = session.execute(user_query, {"user_id": user_id}).fetchone()

                        if user_record and user_record[0]:
                            send_win_notification(user_record[0], lottery_name, win_amt, draw_no)
                        else:
                            logger.info(f"No FCM token found for user {user_id}. Skipping notification.")

                logger.info(f"Successfully processed draw {draw_no} for {lottery_name}")
            except Exception as e:
                logger.error(f"Error processing {lottery_name} tickets for draw {draw_no}: {e}")
        else:
            logger.info(f"No specific handler yet for lottery type: {lottery_name}")


@router.post("/supabase-draw-event")
async def supabase_draw_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    table_name = payload.get("table")
    action_type = payload.get("type")

    if table_name != "jaya_draws":
        logger.info(f"Ignoring webhook for table: {table_name}")
        return {"status": "ignored", "reason": f"Table {table_name} not handled"}

    if action_type not in ("INSERT", "UPDATE"):
        logger.info(f"Ignoring webhook action type: {action_type}")
        return {"status": "ignored", "reason": f"Action {action_type} not handled"}

    background_tasks.add_task(process_new_draw, payload)

    return {"status": "accepted", "message": "Draw processing started in background"}