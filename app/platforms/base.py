"""
Abstract base class for all platform integrations.

Every platform must:
  - Declare a human-readable `name` class attribute.
  - Implement the `publish(message)` coroutine.
  - Use the helper methods `_success_result`, `_failed_result`, and
    `_unconfigured_result` to build standardized `PlatformResult` objects.

Error-handling conventions:
  - Never let platform exceptions propagate uncaught; always return a
    `PlatformResult` with status="failed".
  - Never expose credentials, tokens, or raw HTTP headers in error messages.
  - Use a shared HTTPX `AsyncClient` timeout of 30 seconds.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

import httpx

from app.schemas import PlatformResult

# Default timeout applied to all outbound HTTP requests (seconds)
DEFAULT_TIMEOUT = httpx.Timeout(timeout=30.0)


class BasePlatform(ABC):
    """Abstract base for every social platform integration."""

    #: Human-readable platform name, e.g. "Telegram"
    name: str = "Unknown"

    # ── Abstract interface ──────────────────────────────────────────────────

    @abstractmethod
    async def publish(self, message: str) -> PlatformResult:
        """
        Publish *message* to this platform.

        Returns a `PlatformResult` with one of three statuses:
          - "success"       – post was accepted by the platform API.
          - "failed"        – attempt was made but the API rejected it.
          - "unconfigured"  – credentials are absent; no request was made.
        """

    # ── Shared helper builders ──────────────────────────────────────────────

    def _success_result(
        self,
        *,
        posted_url: str | None = None,
        public_access: bool = False,
        published_at: datetime | None = None,
    ) -> PlatformResult:
        """Build a success result, recording the publish timestamp."""
        ts = published_at or datetime.now(tz=timezone.utc)
        return PlatformResult(
            platform=self.name,
            status="success",
            posted_url=posted_url,
            public_access=public_access,
            date=ts.strftime("%Y-%m-%d"),
            time=ts.strftime("%H:%M:%S"),
            error=None,
        )

    def _failed_result(self, error: str) -> PlatformResult:
        """Build a failed result with a sanitized error message."""
        return PlatformResult(
            platform=self.name,
            status="failed",
            posted_url=None,
            public_access=False,
            date=None,
            time=None,
            error=error,
        )

    def _unconfigured_result(self) -> PlatformResult:
        """Build an unconfigured result when credentials are missing."""
        return PlatformResult(
            platform=self.name,
            status="unconfigured",
            posted_url=None,
            public_access=False,
            date=None,
            time=None,
            error="Platform credentials are not configured.",
        )

    # ── Shared HTTPX client factory ─────────────────────────────────────────

    @staticmethod
    def _make_client(**kwargs) -> httpx.AsyncClient:
        """
        Create a configured HTTPX `AsyncClient`.

        Caller is responsible for using it as an async context manager.
        """
        return httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, **kwargs)
