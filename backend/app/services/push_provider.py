"""
Fournisseur de notifications push (Expo HTTP Push API & Mock pour tests).
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import urllib.request
import urllib.error
import json

from app.models.notification import PushDevice

logger = logging.getLogger(__name__)


@dataclass
class ProviderResponse:
    success: bool
    message_id: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    retryable: bool = False
    deactivate_token: bool = False


class NotificationProvider(ABC):
    """Interface abstraite pour l'envoi de push notifications."""

    @abstractmethod
    def send_push_notification(
        self,
        device: PushDevice,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> ProviderResponse:
        pass


class ExpoPushProvider(NotificationProvider):
    """
    Adaptateur Expo HTTP Push API :
    https://docs.expo.dev/push-notifications/sending-notifications/
    """
    EXPO_API_URL = "https://exp.host/--/api/v2/push/send"

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token

    def send_push_notification(
        self,
        device: PushDevice,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> ProviderResponse:
        push_token = device.push_token
        # Validation basique du format de token Expo
        if not push_token.startswith("ExponentPushToken[") and not push_token.startswith("ExpoPushToken["):
            # Si ce n'est pas un token Expo valide
            return ProviderResponse(
                success=False,
                error_code="InvalidPushToken",
                error_message="Not a valid Expo push token",
                retryable=False,
                deactivate_token=True,
            )

        payload = {
            "to": push_token,
            "title": title,
            "body": body,
            "data": data or {},
            "sound": "default",
            "priority": "high",
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        req = urllib.request.Request(
            self.EXPO_API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=5.0) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                # Expo renvoie {"data": {"status": "ok", "id": "..."}} ou {"data": {"status": "error", ...}}
                ticket = res_data.get("data", {})
                if isinstance(ticket, list) and len(ticket) > 0:
                    ticket = ticket[0]

                if ticket.get("status") == "ok":
                    return ProviderResponse(
                        success=True,
                        message_id=ticket.get("id"),
                    )

                # Statut d'erreur au niveau du ticket
                error_type = ticket.get("details", {}).get("error") or ticket.get("message")
                deactivate = error_type in ("DeviceNotRegistered", "InvalidCredentials")
                retryable = error_type in ("MessageRateExceeded", "InternalServerError")
                return ProviderResponse(
                    success=False,
                    error_code=error_type or "ExpoTicketError",
                    error_message=ticket.get("message"),
                    retryable=retryable,
                    deactivate_token=deactivate,
                )

        except urllib.error.HTTPError as http_err:
            code = http_err.code
            retryable = code in (429, 500, 502, 503, 504)
            return ProviderResponse(
                success=False,
                error_code=f"HTTP_{code}",
                error_message=str(http_err),
                retryable=retryable,
                deactivate_token=False,
            )
        except Exception as exc:
            logger.warning(f"Error sending push to {push_token}: {exc}")
            return ProviderResponse(
                success=False,
                error_code="NetworkError",
                error_message=str(exc),
                retryable=True,
                deactivate_token=False,
            )


class MockPushProvider(NotificationProvider):
    """
    Fournisseur simulé pour les tests automatisés et développements locaux.
    Enregistre les messages envoyés et permet de forcer des erreurs spécifiques.
    """

    def __init__(self):
        self.sent_messages: List[Dict[str, Any]] = []
        self.simulated_errors: Dict[str, ProviderResponse] = {}

    def force_error_for_token(self, token: str, response: ProviderResponse):
        self.simulated_errors[token] = response

    def send_push_notification(
        self,
        device: PushDevice,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> ProviderResponse:
        if device.push_token in self.simulated_errors:
            return self.simulated_errors[device.push_token]

        # Enregistrement du message
        self.sent_messages.append({
            "device_id": device.id,
            "user_id": device.user_id,
            "push_token": device.push_token,
            "title": title,
            "body": body,
            "data": data or {},
        })

        return ProviderResponse(
            success=True,
            message_id=f"mock-msg-{len(self.sent_messages)}",
        )
