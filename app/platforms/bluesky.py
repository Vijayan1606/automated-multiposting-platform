"""
Bluesky (AT Protocol) platform integration.

Authentication uses the XRPC `com.atproto.server.createSession` endpoint
to exchange an identifier + app-password for a short-lived JWT session.
The session's `accessJwt` is then used as a Bearer token for the
`com.atproto.repo.createRecord` call that creates the post.

API documentation:
  https://docs.bsky.app/docs/tutorials/creating-a-post
  https://atproto.com/lexicons/com-atproto-repo

Required environment variables:
  BLUESKY_IDENTIFIER    – handle (e.g. yourname.bsky.social) or DID
  BLUESKY_APP_PASSWORD  – app-specific password from bsky.app settings

Post URL strategy:
  Bluesky returns a `uri` in the form:
    at://did:plc:XXXXX/app.bsky.feed.post/RKEY
  The public web URL is constructed as:
    https://bsky.app/profile/{did}/post/{rkey}
  All Bluesky posts are public by default → public_access = True.
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.platforms.base import BasePlatform
from app.schemas import PlatformResult

_BSKY_HOST = "https://bsky.social"
_SESSION_ENDPOINT = f"{_BSKY_HOST}/xrpc/com.atproto.server.createSession"
_CREATE_RECORD_ENDPOINT = (
    f"{_BSKY_HOST}/xrpc/com.atproto.repo.createRecord"
)


class BlueskyPlatform(BasePlatform):
    """Publishes posts via the Bluesky AT Protocol API."""

    name = "Bluesky"

    async def publish(self, message: str) -> PlatformResult:
        """Authenticate and create a post on Bluesky."""
        if not settings.bluesky_configured:
            return self._unconfigured_result()

        try:
            async with self._make_client() as client:
                # Step 1 – create session (get access token)
                session = await self._create_session(client)
                if isinstance(session, PlatformResult):
                    return session  # auth failed

                access_jwt: str = session["accessJwt"]
                did: str = session["did"]

                # Step 2 – create the post record
                return await self._create_post(
                    client, access_jwt, did, message
                )

        except httpx.TimeoutException:
            return self._failed_result("Request timed out.")
        except httpx.RequestError as exc:
            return self._failed_result(
                f"Network error: {type(exc).__name__}."
            )

    # ── Private helpers ─────────────────────────────────────────────────────

    async def _create_session(
        self, client: httpx.AsyncClient
    ) -> dict | PlatformResult:
        """
        Exchange credentials for an AT Protocol session.

        Returns the session dict on success, or a failed `PlatformResult`.
        """
        response = await client.post(
            _SESSION_ENDPOINT,
            json={
                "identifier": settings.bluesky_identifier,
                "password": settings.bluesky_app_password,
            },
        )

        if response.status_code == 401:
            return self._failed_result(
                "Bluesky authentication failed. "
                "Check BLUESKY_IDENTIFIER and BLUESKY_APP_PASSWORD."
            )

        if response.status_code != 200:
            return self._failed_result(
                f"Bluesky session creation failed "
                f"(HTTP {response.status_code})."
            )

        try:
            return response.json()
        except Exception:
            return self._failed_result(
                "Bluesky returned an unexpected non-JSON session response."
            )

    async def _create_post(
        self,
        client: httpx.AsyncClient,
        access_jwt: str,
        did: str,
        message: str,
    ) -> PlatformResult:
        """Create a Bluesky post record and return a result."""
        from datetime import datetime, timezone

        created_at = datetime.now(tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3] + "Z"  # Bluesky expects millisecond precision + Z suffix

        record = {
            "$type": "app.bsky.feed.post",
            "text": message,
            "createdAt": created_at,
        }

        response = await client.post(
            _CREATE_RECORD_ENDPOINT,
            headers={"Authorization": f"Bearer {access_jwt}"},
            json={
                "repo": did,
                "collection": "app.bsky.feed.post",
                "record": record,
            },
        )

        if response.status_code not in {200, 201}:
            try:
                err_data = response.json()
                err_msg = err_data.get("message", "Unknown error.")
            except Exception:
                err_msg = f"HTTP {response.status_code}"
            return self._failed_result(
                f"Bluesky post creation failed: {err_msg}"
            )

        try:
            data = response.json()
        except Exception:
            return self._failed_result(
                "Bluesky returned a non-JSON response after posting."
            )

        # Build public URL from the AT URI
        # Format: at://did:plc:XXXXX/app.bsky.feed.post/RKEY
        at_uri: str = data.get("uri", "")
        rkey: str = at_uri.split("/")[-1] if at_uri else ""
        post_did: str = data.get("cid", "") or did  # fall back to session DID

        if rkey and did:
            posted_url: str | None = (
                f"https://bsky.app/profile/{did}/post/{rkey}"
            )
        else:
            posted_url = None

        return self._success_result(
            posted_url=posted_url,
            public_access=True,  # Bluesky is public by default
        )
