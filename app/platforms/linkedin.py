"""
LinkedIn platform integration.

Uses the LinkedIn UGC Posts API to publish text shares on behalf of
a member (person) using an OAuth 2.0 access token.

API documentation:
  https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api

Required environment variables:
  LINKEDIN_ACCESS_TOKEN  – OAuth 2.0 Bearer token with scopes:
                           r_liteprofile, w_member_social
  LINKEDIN_PERSON_URN    – Member URN, format: urn:li:person:XXXXXXXX

Obtaining credentials:
  1. Create an app at https://www.linkedin.com/developers/apps
  2. Request the r_liteprofile and w_member_social products
  3. Use the 3-legged OAuth 2.0 flow to obtain an access token
  4. The person URN can be retrieved via GET /v2/me

Post URL strategy:
  LinkedIn's UGC Posts API returns the post ID in the response `id` field,
  formatted as: urn:li:ugcPost:XXXXXXXX
  The public URL is: https://www.linkedin.com/feed/update/{id}

Public access:
  LinkedIn posts made via the API default to PUBLIC visibility.
  We confirm this from the response or assume it based on the payload.

Rate limit handling:
  LinkedIn returns HTTP 429 when rate limited. We report with retry guidance.

Note on token expiry:
  LinkedIn access tokens expire (typically 60 days). The integration
  handles 401/403 responses with clear error messaging.
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.platforms.base import BasePlatform
from app.schemas import PlatformResult

_LINKEDIN_API_BASE = "https://api.linkedin.com/v2"
_UGC_POSTS_ENDPOINT = f"{_LINKEDIN_API_BASE}/ugcPosts"


class LinkedInPlatform(BasePlatform):
    """Publishes text shares via the LinkedIn UGC Posts API."""

    name = "LinkedIn"

    async def publish(self, message: str) -> PlatformResult:
        """Create a UGC post on LinkedIn."""
        if not settings.linkedin_configured:
            return self._unconfigured_result()

        headers = {
            "Authorization": f"Bearer {settings.linkedin_access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        }

        payload = {
            "author": settings.linkedin_person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": message,
                    },
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            },
        }

        try:
            async with self._make_client() as client:
                response = await client.post(
                    _UGC_POSTS_ENDPOINT, json=payload, headers=headers
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
        """Interpret the LinkedIn API response."""
        if response.status_code == 401:
            return self._failed_result(
                "LinkedIn authentication failed. "
                "LINKEDIN_ACCESS_TOKEN may be expired or invalid."
            )

        if response.status_code == 403:
            return self._failed_result(
                "LinkedIn access forbidden. "
                "Ensure the token has 'w_member_social' scope and "
                "LINKEDIN_PERSON_URN is correct."
            )

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "unknown")
            return self._failed_result(
                f"LinkedIn rate limit reached. "
                f"Retry after {retry_after} seconds."
            )

        if response.status_code == 422:
            try:
                error_data = response.json()
                detail = error_data.get(
                    "message", error_data.get("error", "Validation error.")
                )
            except Exception:
                detail = "Validation error."
            return self._failed_result(f"LinkedIn validation error: {detail}")

        if response.status_code not in {200, 201}:
            try:
                error_data = response.json()
                detail = error_data.get(
                    "message", error_data.get("error", "Unknown error.")
                )
            except Exception:
                detail = f"HTTP {response.status_code}"
            return self._failed_result(f"LinkedIn API error: {detail}")

        # LinkedIn returns the post URN in the `id` field of the response body
        # or in the `X-RestLi-Id` response header (both may be present).
        post_urn: str | None = None

        # Prefer the response body
        try:
            data = response.json()
            post_urn = data.get("id")
        except Exception:
            pass

        # Fall back to the X-RestLi-Id header
        if not post_urn:
            post_urn = response.headers.get("x-restli-id")

        # Construct public URL
        posted_url: str | None = None
        if post_urn:
            # Encode the URN for use in a URL
            encoded_urn = post_urn.replace(":", "%3A")
            posted_url = (
                f"https://www.linkedin.com/feed/update/{encoded_urn}"
            )

        return self._success_result(
            posted_url=posted_url,
            public_access=True,  # payload specifies PUBLIC visibility
        )
