from app.services.firebase import init_firebase
from firebase_admin import messaging

init_firebase()

real_token = "ckJ9wrjMQLyHBQWgFNr1Bb:APA91bH1Tt9X2rNuyKIWEs2JKKE75r2ewaCHKjjlQZaVjJ4l7n4faTSiNw37N8dwkXEq6-N6uq05f-PJ-Xv7joWFcJWL4NlwTpjII3CGOCwsI-8Gj1EKlcM"

message = messaging.MulticastMessage(
    tokens=[real_token],
    notification=messaging.Notification(
        title="Test",
        body="Test notification",
    ),
)

try:
    response = messaging.send_each_for_multicast(message)
    print("Success:", response.success_count)
    print("Failed:", response.failure_count)
    for idx, r in enumerate(response.responses):
        if not r.success:
            print("Error code:", r.exception.code)
            print("Error message:", r.exception)
except Exception as e:
    print("Exception:", type(e).__name__)
    print("Detail:", str(e))