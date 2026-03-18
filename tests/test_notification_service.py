"""Tests for notification_service — uses mocks so no real Firebase credentials needed."""
import pytest
from unittest.mock import patch, MagicMock


# Patch firebase_admin before notification_service is imported so we avoid
# the real Certificate/initialize_app calls during tests.
@pytest.fixture(autouse=True)
def mock_firebase(monkeypatch):
    """Stub out the entire firebase_admin module for unit testing."""
    import sys

    # Build a minimal fake firebase_admin module
    fake_firebase = MagicMock()
    fake_firebase._apps = {}  # empty → triggers initialisation branch

    fake_messaging = MagicMock()
    fake_messaging.UnregisteredError = Exception  # so the except clause works

    fake_firebase.messaging = fake_messaging
    fake_firebase.credentials = MagicMock()

    sys.modules["firebase_admin"] = fake_firebase
    sys.modules["firebase_admin.credentials"] = fake_firebase.credentials
    sys.modules["firebase_admin.messaging"] = fake_messaging

    yield fake_firebase, fake_messaging

    # Clean up so other test modules start fresh
    sys.modules.pop("firebase_admin", None)
    sys.modules.pop("firebase_admin.credentials", None)
    sys.modules.pop("firebase_admin.messaging", None)
    sys.modules.pop("app.services.notification_service", None)


def _import_service():
    """Import (or re-import) notification_service after mocks are in place."""
    import importlib
    import app.services.notification_service as ns
    importlib.reload(ns)
    return ns


def test_send_win_notification_calls_firebase(mock_firebase):
    """send_win_notification should call messaging.send with the correct token."""
    _, fake_messaging = mock_firebase
    fake_messaging.send.return_value = "projects/test/messages/abc123"

    ns = _import_service()
    ns.send_win_notification(
        fcm_token="test-device-token",
        lottery_name="govisetha",
        win_amount=2_000_000.0,
        draw_no=1234,
    )

    fake_messaging.send.assert_called_once()
    call_args = fake_messaging.send.call_args[0][0]  # first positional arg

    # The Message object should have been constructed with the right token
    fake_messaging.Message.assert_called_once()
    kwargs = fake_messaging.Message.call_args.kwargs
    assert kwargs["token"] == "test-device-token"
    assert kwargs["data"]["lottery_name"] == "govisetha"
    assert kwargs["data"]["draw_no"] == "1234"
    assert kwargs["data"]["win_amount"] == "2000000.0"


def test_send_win_notification_empty_token_skips(mock_firebase, caplog):
    """send_win_notification should skip gracefully when token is empty."""
    _, fake_messaging = mock_firebase

    ns = _import_service()
    with caplog.at_level("WARNING"):
        ns.send_win_notification(
            fcm_token="",
            lottery_name="govisetha",
            win_amount=2_000_000.0,
            draw_no=1234,
        )

    fake_messaging.send.assert_not_called()
    assert "empty token" in caplog.text


def test_send_win_notification_unregistered_token(mock_firebase, caplog):
    """UnregisteredError (stale token) should be caught and logged, not raised."""
    _, fake_messaging = mock_firebase
    fake_messaging.UnregisteredError = RuntimeError  # use a real exception class
    fake_messaging.send.side_effect = RuntimeError("Token not registered")

    ns = _import_service()
    # Should NOT raise
    ns.send_win_notification(
        fcm_token="stale-token",
        lottery_name="govisetha",
        win_amount=40.0,
        draw_no=999,
    )
