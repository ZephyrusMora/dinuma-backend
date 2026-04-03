import os
import logging
import json

import firebase_admin
from firebase_admin import credentials, messaging

logger = logging.getLogger(__name__)

_CRED_JSON = os.getenv("FIREBASE_CREDENTIALS_JSON")
_CRED_PATH = os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase-credentials.json")

if not firebase_admin._apps:
    try:
        if _CRED_JSON:
            try:
                cert_dict = json.loads(_CRED_JSON)
                cred = credentials.Certificate(cert_dict)
                logger.info("[Firebase] Initializing from FIREBASE_CREDENTIALS_JSON (Config Var)")
            except json.JSONDecodeError:
                logger.error("[Firebase] Failed to parse FIREBASE_CREDENTIALS_JSON as valid JSON")
                raise
        else:
            if not os.path.exists(_CRED_PATH):
                logger.warning("[Firebase] Credentials file not found at: %s", _CRED_PATH)
            cred = credentials.Certificate(_CRED_PATH)
            logger.info("[Firebase] Initializing from file: %s", _CRED_PATH)

        firebase_admin.initialize_app(cred)
        logger.info("[Firebase] Admin SDK initialized successfully")
    except Exception:
        logger.exception("[Firebase] Failed to initialize Admin SDK.")


def send_win_notification(
    fcm_token: str,
    lottery_name: str,
    win_amount: float,
    draw_no: int,
) -> None:
    """Send a push notification to a single device when their ticket wins."""
    if not fcm_token:
        logger.warning("[FCM] send_win_notification called with empty token, skipping.")
        return

    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title="🎉 You Won!",
                body=(
                    f"Your {lottery_name.capitalize()} ticket #{draw_no} "
                    f"won Rs {win_amount:,.2f}!"
                ),
            ),
            data={
                "type": "WIN",
                "lottery_name": lottery_name,
                "draw_no": str(draw_no),
                "win_amount": str(win_amount),
            },
            token=fcm_token,
            android=messaging.AndroidConfig(
                priority="high",
                notification=messaging.AndroidNotification(
                    sound="default",
                    channel_id="wins",
                ),
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(sound="default", badge=1),
                ),
            ),
        )

        response = messaging.send(message)
        logger.info("[FCM] Notification sent successfully. Message ID: %s", response)

    except messaging.UnregisteredError:
        logger.warning(
            "[FCM] Token unregistered for draw %s. Token: %s",
            draw_no,
            fcm_token,
        )
        from app.services.db import deactivate_token
        deactivate_token(fcm_token)

    except messaging.SenderIdMismatchError:
        logger.warning(
            "[FCM] Sender ID mismatch for token %s. Deactivating.",
            fcm_token,
        )
        from app.services.db import deactivate_token
        deactivate_token(fcm_token)

    except Exception:
        logger.exception("[FCM] Failed to send win notification for draw %s", draw_no)