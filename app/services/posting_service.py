"""
Posting service.

Orchestrates concurrent publishing to all five social platforms using
`asyncio.gather(return_exceptions=True)` to ensure that a failure on
one platform never cancels or interferes with the others.

Design decisions:
  - Platforms are instantiated once at service construction time.
  - Each platform.publish() is independently wrapped in exception handling
    so that unexpected bugs in one integration cannot surface as uncaught
    exceptions in the gather result.
  - `success` is True only when every configured platform publishes
    successfully. Unconfigured platforms do not count against success.
  - If NO platforms are configured, `success` is False and every result
    has status="unconfigured".
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.platforms.base import BasePlatform
from app.platforms.bluesky import BlueskyPlatform
from app.platforms.linkedin import LinkedInPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.reddit import RedditPlatform
from app.platforms.telegram import TelegramPlatform
from app.schemas import PlatformResult, PostingResponse

logger = logging.getLogger(__name__)


class PostingService:
    """
    Coordinates concurrent posting across all registered platforms.

    Usage::

        service = PostingService()
        response = await service.post_to_all("Your message https://url.com")
    """

    def __init__(self) -> None:
        self._platforms: list[BasePlatform] = [
            TelegramPlatform(),
            BlueskyPlatform(),
            MastodonPlatform(),
            LinkedInPlatform(),
            RedditPlatform(),
        ]

    async def post_to_all(self, message: str) -> PostingResponse:
        """
        Publish *message* to all registered platforms concurrently.

        Each platform is invoked independently; a failure on one platform
        does not affect the others. Unexpected exceptions from individual
        platforms are caught and converted to failed PlatformResult objects.

        Returns a `PostingResponse` whose `success` field is True only
        when every configured platform published successfully.
        """
        logger.info(
            "Starting concurrent publish to %d platforms.",
            len(self._platforms),
        )

        # Wrap each platform publish call with individual exception handling
        tasks = [
            self._safe_publish(platform, message)
            for platform in self._platforms
        ]

        raw_results: list[Any] = await asyncio.gather(
            *tasks, return_exceptions=True
        )

        results: list[PlatformResult] = []
        for platform, raw in zip(self._platforms, raw_results):
            if isinstance(raw, PlatformResult):
                results.append(raw)
                logger.info(
                    "Platform %s → %s", platform.name, raw.status
                )
            else:
                # This branch should not normally be reached because
                # _safe_publish catches all exceptions, but we include
                # it as a safety net.
                error_msg = (
                    f"Unexpected error: {type(raw).__name__}: {raw}"
                    if isinstance(raw, Exception)
                    else "Unexpected internal error."
                )
                logger.error(
                    "Unhandled exception from %s: %s",
                    platform.name,
                    error_msg,
                )
                results.append(
                    PlatformResult(
                        platform=platform.name,
                        status="failed",
                        posted_url=None,
                        public_access=False,
                        date=None,
                        time=None,
                        error="An unexpected internal error occurred.",
                    )
                )

        # Determine overall success:
        # True only when every result with status != "unconfigured"
        # has status == "success".
        active_results = [r for r in results if r.status != "unconfigured"]

        if not active_results:
            # No platforms are configured at all
            overall_success = False
        else:
            overall_success = all(
                r.status == "success" for r in active_results
            )

        logger.info("Overall posting success: %s", overall_success)
        return PostingResponse(success=overall_success, results=results)

    # ── Private helpers ─────────────────────────────────────────────────────

    async def _safe_publish(
        self, platform: BasePlatform, message: str
    ) -> PlatformResult:
        """
        Invoke `platform.publish()` with a top-level exception guard.

        Any unexpected exception (e.g. a programming bug in a platform
        integration) is caught here and returned as a failed result,
        preventing it from propagating through asyncio.gather.
        """
        try:
            return await platform.publish(message)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "Unexpected exception in %s.publish(): %s",
                platform.name,
                exc,
            )
            return PlatformResult(
                platform=platform.name,
                status="failed",
                posted_url=None,
                public_access=False,
                date=None,
                time=None,
                error="An unexpected internal error occurred.",
            )
