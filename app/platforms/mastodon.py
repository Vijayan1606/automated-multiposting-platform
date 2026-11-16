"""
Mastodon platform integration.

Uses the Mastodon REST API v1 to publish statuses (toots).

API documentation: https://docs.joinmastodon.org/methods/statuses/

Required environment variables:
  MASTODON_INSTANCE_URL  – base URL of your Mastodon instance,
                           e.g. https://mastodon.social
  MASTODON_ACCESS_TOKEN  – access token obtained from your instance's
                           developer settings (Preferences → Development)

Post URL strategy:
  The API response includes a `url` field with the full public URL of
  the published status.

Public access:
  Determined by the `visibility` field in the response.
  'public' → public_access = True
  'unlisted', 'private', 'direct' → public_access = False

Rate limit handling:
  Mastodon returns HTTP 429 with a Retry-After header when rate limited.
  We report this as a failed result with an informative message.
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.platforms.base import BasePlatform
from app.schemas import PlatformResult


class MastodonPlatform(BasePlatform):
    """Publishes statuses via the Mastodon API."""

    name = "Mastodon"

    async def publish(self, message: str) -> PlatformResult:
        """Post a status to the configured Mastodon instance."""
        if not settings.mastodon_configured:
            return self._unconfigured_result()

        # Normalise instance URL (strip trailing slash)
        instance_url = settings.mastodon_instance_url.rstrip("/")
        endpoint = f"{instance_url}/api/v1/statuses"

        headers = {
            "Authorization": f"Bearer {settings.mastodon_access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "status": message,
            "visibility": "public",
        }

        try:
            async with self._make_client() as client:
                response = await client.post(
                    endpoint, json=payload, headers=headers
                )
        except httpx.TimeoutException:
            return self._failed_result("Request timed out.")
        except httpx.RequestError as exc:
            return self._failed_result(
                f"Network error: {type(exc).__name__}."
            )

        return self._parse_response(response)

    # ── Private helpers ─────────────────────────────────────────────────────

    def _parse_response(self, response: httpx.Response) -> PlatformResult:
        """Interpret the Mastodon API response."""
        if response.status_code == 401:
            return self._failed_result(
                "Mastodon authentication failed. "
                "Check MASTODON_ACCESS_TOKEN."
            )

        if response.status_code == 403:
            return self._failed_result(
                "Mastodon access forbidden. "
                "Ensure the token has 'write:statuses' scope."
            )

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "unknown")
            return self._failed_result(
                f"Mastodon rate limit reached. "
                f"Retry after {retry_after} seconds."
            )

        if response.status_code == 422:
            # Validation errors from Mastodon
            try:
                error_data = response.json()
                detail = error_data.get("error", "Validation error.")
            except Exception:
                detail = "Validation error."
            return self._failed_result(f"Mastodon validation error: {detail}")

        if response.status_code not in {200, 201}:
            return self._failed_result(
                f"Mastodon API error (HTTP {response.status_code})."
            )

        try:
            data = response.json()
        except Exception:
            return self._failed_result(
                "Mastodon returned an unexpected non-JSON response."
            )

        posted_url: str | None = data.get("url")
        visibility: str = data.get("visibility", "")
        is_public = visibility == "public"

        return self._success_result(
            posted_url=posted_url,
            public_access=is_public,
        )
