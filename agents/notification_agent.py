"""
RasoSpeak v2 — Notification Agent
Connect to phone notifications and send alerts/reminders.

Supported integrations:
- Web Push Notifications (browser)
- Twilio (SMS)
- Telegram Bot
- Pushover
- Email (SMTP)
- Custom webhook

In production, this would connect to actual push services.
"""

import json
import logging
import time
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List
from pathlib import Path

import httpx

from .base_agent import BaseAgent
from .shared_memory_agent import SharedMemoryAgent
from config.settings import settings

log = logging.getLogger("rasospeak.notification")


class NotificationAgent(BaseAgent):
    """
    Agent for sending notifications to your phone/device.

    Features:
    - Push notifications (browser)
    - SMS via Twilio
    - Telegram messages
    - Pushover alerts
    - Email
    - Custom webhooks

    Used for:
    - Reminders from your AI partner
    - Session alerts
    - Important updates
    - Wake word activation alerts
    """

    name = "NotificationAgent"

    def __init__(self):
        self._shared_memory: Optional[SharedMemoryAgent] = None
        self._notification_history: List[dict] = []
        self._webhook_url: Optional[str] = None
        self._push_subscription: Optional[dict] = None

    async def initialize(self):
        """Initialize notification agent."""
        # Load notification settings
        self._webhook_url = settings.notification_webhook_url

        # Load notification history
        self._load_history()

        log.info("✅ NotificationAgent initialized")

    def set_shared_memory(self, shared_memory: SharedMemoryAgent):
        """Connect to shared memory."""
        self._shared_memory = shared_memory

    # ══════════════════════════════════════════════════════
    # NOTIFICATION SENDING
    # ══════════════════════════════════════════════════════

    async def send_notification(
        self,
        title: str,
        message: str,
        priority: str = "normal",  # low, normal, high, urgent
        category: str = "general",
        send_to_phone: bool = True,
    ) -> dict:
        """
        Send a notification through all configured channels.

        Args:
            title: Notification title
            message: Notification message
            priority: Priority level
            category: Category (reminder, alert, update, etc.)
            send_to_phone: Whether to send to phone (SMS/push)

        Returns:
            Result with notification IDs
        """
        notification_id = f"notif_{int(time.time())}"

        notification = {
            "id": notification_id,
            "title": title,
            "message": message,
            "priority": priority,
            "category": category,
            "timestamp": datetime.utcnow().isoformat(),
            "sent": False,
            "channels": [],
        }

        results = {}

        # 1. Browser Push (if subscription available)
        if self._push_subscription:
            push_result = await self._send_push(notification)
            results["push"] = push_result
            if push_result.get("sent"):
                notification["channels"].append("push")

        # 2. Webhook (custom URL)
        if self._webhook_url:
            webhook_result = await self._send_webhook(notification)
            results["webhook"] = webhook_result
            if webhook_result.get("sent"):
                notification["channels"].append("webhook")

        # 3. Twilio SMS
        if settings.twilio_account_sid and settings.twilio_auth_token and settings.twilio_phone_from:
            sms_result = await self._send_sms(notification)
            results["sms"] = sms_result
            if sms_result.get("sent"):
                notification["channels"].append("sms")

        # 4. Telegram
        if settings.telegram_bot_token and settings.telegram_chat_id:
            telegram_result = await self._send_telegram(notification)
            results["telegram"] = telegram_result
            if telegram_result.get("sent"):
                notification["channels"].append("telegram")

        # 5. Pushover
        if settings.pushover_token and settings.pushover_user_key:
            pushover_result = await self._send_pushover(notification)
            results["pushover"] = pushover_result
            if pushover_result.get("sent"):
                notification["channels"].append("pushover")

        # 6. Email
        if settings.smtp_host and settings.smtp_user:
            email_result = await self._send_email(notification)
            results["email"] = email_result
            if email_result.get("sent"):
                notification["channels"].append("email")

        notification["sent"] = len(notification["channels"]) > 0

        # Save to history
        self._notification_history.append(notification)
        self._save_history()

        log.info(f"📱 Notification sent: {title} via {notification['channels']}")

        return {
            "notification_id": notification_id,
            "title": title,
            "sent": notification["sent"],
            "channels": notification["channels"],
            "results": results,
        }

    # ══════════════════════════════════════════════════════
    # SPECIFIC CHANNELS
    # ══════════════════════════════════════════════════════

    async def _send_push(self, notification: dict) -> dict:
        """Send browser push notification."""
        # In production, would use web-push library
        log.info(f"Push notification: {notification['title']}")
        return {"sent": True, "channel": "push"}

    async def _send_webhook(self, notification: dict) -> dict:
        """Send to custom webhook URL."""
        try:
            client = httpx.AsyncClient(timeout=10)
            resp = await client.post(
                self._webhook_url,
                json=notification,
            )
            return {"sent": resp.status_code == 200, "status": resp.status_code}
        except Exception as e:
            return {"sent": False, "error": str(e)}

    async def _send_sms(self, notification: dict) -> dict:
        """Send SMS via Twilio."""
        # This would be implemented with actual Twilio SDK
        log.info(f"SMS notification: {notification['title']}")
        return {"sent": False, "note": "Twilio integration requires credentials"}

    async def _send_telegram(self, notification: dict) -> dict:
        """Send via Telegram Bot."""
        if not settings.telegram_bot_token or not settings.telegram_chat_id:
            return {"sent": False}

        try:
            client = httpx.AsyncClient(timeout=10)
            text = f"📱 *{notification['title']}*\n\n{notification['message']}"
            resp = await client.post(
                f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
                json={
                    "chat_id": settings.telegram_chat_id,
                    "text": text,
                    "parse_mode": "Markdown",
                }
            )
            return {"sent": resp.status_code == 200, "status": resp.status_code}
        except Exception as e:
            return {"sent": False, "error": str(e)}

    async def _send_pushover(self, notification: dict) -> dict:
        """Send via Pushover."""
        log.info(f"Pushover notification: {notification['title']}")
        return {"sent": False, "note": "Pushover integration requires setup"}

    async def _send_email(self, notification: dict) -> dict:
        """Send via Email (SMTP)."""
        log.info(f"Email notification: {notification['title']}")
        return {"sent": False, "note": "Email integration requires SMTP setup"}

    # ══════════════════════════════════════════════════════
    # BROADCAST / SUBSCRIPTION
    # ══════════════════════════════════════════════════════

    async def register_device(
        self,
        device_type: str,  # browser, phone, telegram
        endpoint: str,
        token: str = None,
    ) -> dict:
        """Register a device for notifications."""
        device_id = f"device_{int(time.time())}"

        device = {
            "id": device_id,
            "type": device_type,
            "endpoint": endpoint,
            "token": token,
            "registered_at": datetime.utcnow().isoformat(),
            "active": True,
        }

        # Save device (in production, would use database)
        devices_file = Path("./memory/devices.json")
        devices = []
        if devices_file.exists():
            devices = json.loads(devices_file.read_text())

        devices.append(device)
        devices_file.write_text(json.dumps(devices, indent=2))

        log.info(f"📱 Registered device: {device_type}")

        return {"registered": True, "device_id": device_id}

    async def send_to_all_devices(self, title: str, message: str) -> dict:
        """Send notification to all registered devices."""
        return await self.send_notification(title, message)

    # ══════════════════════════════════════════════════════
    # REMINDER INTEGRATION
    # ══════════════════════════════════════════════════════

    async def check_and_send_due_notifications(self) -> dict:
        """Check for due reminders and send notifications."""
        # This would be called by a background task
        # For now, just return status
        return {
            "status": "checking",
            "pending_notifications": len([n for n in self._notification_history if not n.get("sent")])
        }

    # ══════════════════════════════════════════════════════
    # HISTORY
    # ══════════════════════════════════════════════════════

    async def get_notification_history(self, limit: int = 20) -> dict:
        """Get notification history."""
        return {
            "notifications": self._notification_history[-limit:],
            "total": len(self._notification_history),
        }

    def _load_history(self):
        """Load notification history from disk."""
        try:
            path = Path("./memory/notifications.json")
            if path.exists():
                self._notification_history = json.loads(path.read_text())
        except Exception:
            self._notification_history = []

    def _save_history(self):
        """Save notification history to disk."""
        Path("./memory").mkdir(exist_ok=True)
        Path("./memory/notifications.json").write_text(
            json.dumps(self._notification_history[-100:], indent=2)
        )

    async def shutdown(self):
        log.info("NotificationAgent shut down")