import os
import logging

import firebase_admin
from firebase_admin import credentials, messaging

from app.services.firebase import init_firebase

logger = logging.getLogger(__name__)

# Run init logic
try:
    init_firebase()
except Exception:
    logger.exception("[Firebase] NotificationService failed to initialize during module load.")


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

    except Exception:
        logger.exception("[FCM] Failed to send win notification for draw %s", draw_no)