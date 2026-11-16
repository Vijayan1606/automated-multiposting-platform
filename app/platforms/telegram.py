"""
Telegram platform integration.

Uses the Telegram Bot API to send messages to a channel or group.

API documentation: https://core.telegram.org/bots/api#sendmessage

Required environment variables:
  TELEGRAM_BOT_TOKEN  – token obtained from @BotFather
  TELEGRAM_CHAT_ID    – numeric ID of the target channel/group
                        (use @username for public channels, or the
                         numeric ID for private groups/channels)

Post URL strategy:
  Telegram's sendMessage response includes `message_id` and `chat.id`.
  - For public channels  → https://t.me/{username}/{message_id}
  - For private chats    → https://t.me/c/{abs(chat_id)}/{message_id}
  Public access is True only for public channels (chat type "channel"
  with a username set).

Authentication errors (401), forbidden (403), and unknown chat (400)
are reported as failed results with sanitized messages.
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.platforms.base import BasePlatform
from app.schemas import PlatformResult

_BASE_URL = "https://api.telegram.org"


class TelegramPlatform(BasePlatform):
    """Publishes messages via the Telegram Bot API."""

    name = "Telegram"

    async def publish(self, message: str) -> PlatformResult:
        """Send *message* to the configured Telegram chat."""
        if not settings.telegram_configured:
            return self._unconfigured_result()

        url = (
            f"{_BASE_URL}/bot{settings.telegram_bot_token}/sendMessage"
        )
        payload = {
            "chat_id": settings.telegram_chat_id,
            "text": message,
            # HTML parse mode allows <a href="..."> links but we keep
            # plain text to avoid injection issues with user content.
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        try:
            async with self._make_client() as client:
                response = await client.post(url, json=payload)
        except httpx.TimeoutException:
            return self._failed_result("Request timed out.")
        except httpx.RequestError as exc:
            return self._failed_result(
                f"Network error: {type(exc).__name__}."
            )

        return self._parse_response(response)

    # ── Private helpers ─────────────────────────────────────────────────────

    def _parse_response(self, response: httpx.Response) -> PlatformResult:
        """Interpret the Telegram API response."""
        # Sanitise: never log or expose the bot token from the URL.
        if response.status_code == 401:
            return self._failed_result(
                "Telegram authentication failed. Check TELEGRAM_BOT_TOKEN."
            )

        try:
            data = response.json()
        except Exception:
            return self._failed_result(
                f"Unexpected non-JSON response (HTTP {response.status_code})."
            )

        if not data.get("ok"):
            description = data.get("description", "Unknown error.")
            error_code = data.get("error_code", response.status_code)
            return self._failed_result(
                f"Telegram API error {error_code}: {description}"
            )

        result_data = data.get("result", {})
        message_id: int = result_data.get("message_id", 0)
        chat = result_data.get("chat", {})
        chat_id: int = chat.get("id", 0)
        chat_username: str = chat.get("username", "")
        chat_type: str = chat.get("type", "")

        # Determine post URL and public access
        is_public_channel = (
            chat_type == "channel" and bool(chat_username)
        )

        if is_public_channel and message_id:
            posted_url: str | None = (
                f"https://t.me/{chat_username}/{message_id}"
            )
        elif message_id and chat_id:
            # For supergroups / private channels – strip the -100 prefix
            abs_chat_id = abs(chat_id)
            if str(abs_chat_id).startswith("100"):
                abs_chat_id = int(str(abs_chat_id)[3:])
            posted_url = f"https://t.me/c/{abs_chat_id}/{message_id}"
        else:
            posted_url = None

        return self._success_result(
            posted_url=posted_url,
            public_access=is_public_channel,
        )
