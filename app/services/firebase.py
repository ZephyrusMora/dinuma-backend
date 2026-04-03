import logging
import os
import firebase_admin
from firebase_admin import credentials, messaging
from dotenv import load_dotenv
import json

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '..', '.env'))

logger = logging.getLogger(__name__)

_initialized = False


def init_firebase():
    global _initialized
    if _initialized:
        return

    # Check for direct JSON string in environment variable (for Heroku)
    cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
    cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH")

    if not cred_json and not cred_path:
        raise RuntimeError("Neither FIREBASE_CREDENTIALS_JSON nor FIREBASE_CREDENTIALS_PATH set")

    try:
        # Try to get existing app first (initialized by notification_service.py)
        firebase_admin.get_app()
        logger.info("Firebase already initialized, reusing existing app")
    except ValueError:
        # No existing app — initialize fresh
        if cred_json:
            try:
                # Initialize using a dictionary (parsed JSON string)
                cert_dict = json.loads(cred_json)
                cred = credentials.Certificate(cert_dict)
                logger.info("Firebase initializing using FIREBASE_CREDENTIALS_JSON")
            except json.JSONDecodeError:
                logger.error("Failed to parse FIREBASE_CREDENTIALS_JSON as valid JSON")
                raise
        else:
            if not os.path.exists(cred_path):
                raise RuntimeError(f"Firebase credentials file not found at: {cred_path}")
            cred = credentials.Certificate(cred_path)
            logger.info("Firebase initializing using FIREBASE_CREDENTIALS_PATH: %s", cred_path)

        firebase_admin.initialize_app(cred)
        logger.info("Firebase initialized successfully")

    _initialized = True


def send_draw_notification(lottery_name: str, draw_no: int, tokens: list[str]) -> None:
    """Send a push notification for a new draw result to a list of FCM tokens."""
    if not tokens:
        logger.info("No tokens to notify for %s draw %s", lottery_name, draw_no)
        return

    from app.services.db import deactivate_token  # avoid circular import

    message = messaging.MulticastMessage(
        tokens=tokens,
        notification=messaging.Notification(
            title=f"New {lottery_name.replace('-', ' ').title()} Result!",
            body=f"Draw #{draw_no} results are now available. Check your numbers!",
        ),
        data={
            "lottery_name": lottery_name,
            "draw_no": str(draw_no),
            "type": "new_draw",
        },
        android=messaging.AndroidConfig(priority="high"),
        apns=messaging.APNSConfig(
            payload=messaging.APNSPayload(
                aps=messaging.Aps(sound="default")
            )
        ),
    )

    try:
        response = messaging.send_each_for_multicast(message)
        logger.info(
            "[%s] Notifications — success: %d, failed: %d",
            lottery_name,
            response.success_count,
            response.failure_count,
        )
        for idx, r in enumerate(response.responses):
            if not r.success:
                code = r.exception.code if r.exception else "unknown"
                logger.warning("Token %d failed: %s", idx, code)
                if code in (
                    "registration-token-not-registered",
                    "invalid-argument",
                    "invalid-registration-token",
                ):
                    deactivate_token(tokens[idx])
                    logger.info("Deactivated stale token at index %d", idx)
    except Exception:
        logger.exception("Failed to send multicast notification for %s", lottery_name)