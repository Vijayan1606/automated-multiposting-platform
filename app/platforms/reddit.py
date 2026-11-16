"""
Reddit platform integration.

Uses the Reddit OAuth2 Password flow to authenticate and the
`api/submit` endpoint to create a link or text post.

API documentation:
  https://www.reddit.com/dev/api/#POST_api_submit
  https://github.com/reddit-archive/reddit/wiki/OAuth2-Quick-Start-Example

Required environment variables:
  REDDIT_CLIENT_ID      – from https://www.reddit.com/prefs/apps (script app)
  REDDIT_CLIENT_SECRET  – script app secret
  REDDIT_USERNAME       – your Reddit account username
  REDDIT_PASSWORD       – your Reddit account password
  REDDIT_USER_AGENT     – unique identifier string, format:
                          <platform>:<app-id>:<version> (by /u/<username>)
  REDDIT_SUBREDDIT      – target subreddit name (without r/ prefix)

Post type:
  Since the message is a text with a URL, we submit a 'link' post
  if the message contains only a URL with brief text; otherwise
  we fall back to a 'self' (text) post using the full message.
  Specifically, we always submit a self-post with the message as the
  body for maximum compatibility and to include the full context.

Post URL strategy:
  Reddit's submit API returns a JSON response containing
  `json.data.url` with the full permalink URL for the submission.
  We use this directly.

Public access:
  Posts to public subreddits are publicly accessible → public_access = True.

Rate limit handling:
  Reddit enforces one post per 10 minutes per subreddit for some accounts.
  HTTP 429 or specific error messages (RATELIMIT) are handled gracefully.

Important notes:
  - New Reddit accounts may need to verify email before posting.
  - Some subreddits require account age or karma minimums.
  - The User-Agent must comply with Reddit's API rules.
"""

from __future__ import annotations

import httpx

from app.config import settings
from app.platforms.base import BasePlatform
from app.schemas import PlatformResult

_REDDIT_TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
_REDDIT_SUBMIT_URL = "https://oauth.reddit.com/api/submit"
_REDDIT_BASE_URL = "https://www.reddit.com"


class RedditPlatform(BasePlatform):
    """Publishes posts via the Reddit OAuth2 API."""

    name = "Reddit"

    async def publish(self, message: str) -> PlatformResult:
        """Authenticate and submit a post to the configured subreddit."""
        if not settings.reddit_configured:
            return self._unconfigured_result()

        try:
            async with self._make_client() as client:
                # Step 1 – obtain OAuth2 access token
                token_result = await self._get_access_token(client)
                if isinstance(token_result, PlatformResult):
                    return token_result

                access_token: str = token_result

                # Step 2 – submit the post
                return await self._submit_post(client, access_token, message)

        except httpx.TimeoutException:
            return self._failed_result("Request timed out.")
        except httpx.RequestError as exc:
            return self._failed_result(
                f"Network error: {type(exc).__name__}."
            )

    # ── Private helpers ─────────────────────────────────────────────────────

    async def _get_access_token(
        self, client: httpx.AsyncClient
    ) -> str | PlatformResult:
        """
        Obtain a Reddit OAuth2 access token using the password flow.

        Returns the token string on success, or a failed `PlatformResult`.
        """
        response = await client.post(
            _REDDIT_TOKEN_URL,
            data={
                "grant_type": "password",
                "username": settings.reddit_username,
                "password": settings.reddit_password,
            },
            auth=(settings.reddit_client_id, settings.reddit_client_secret),
            headers={"User-Agent": settings.reddit_user_agent},
        )

        if response.status_code == 401:
            return self._failed_result(
                "Reddit authentication failed. "
                "Check REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET."
            )

        if response.status_code != 200:
            return self._failed_result(
                f"Reddit token request failed (HTTP {response.status_code})."
            )

        try:
            data = response.json()
        except Exception:
            return self._failed_result(
                "Reddit returned an unexpected non-JSON token response."
            )

        if "error" in data:
            return self._failed_result(
                f"Reddit token error: {data['error']}. "
                "Verify REDDIT_USERNAME and REDDIT_PASSWORD."
            )

        access_token: str | None = data.get("access_token")
        if not access_token:
            return self._failed_result(
                "Reddit did not return an access token in the response."
            )

        return access_token

    async def _submit_post(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        message: str,
    ) -> PlatformResult:
        """Submit a self-post to the configured subreddit."""
        subreddit = settings.reddit_subreddit.lstrip("r/").strip()

        response = await client.post(
            _REDDIT_SUBMIT_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "User-Agent": settings.reddit_user_agent,
            },
            data={
                "api_type": "json",
                "kind": "self",
                "sr": subreddit,
                "title": message[:300],  # Reddit title max 300 chars
                "text": message,         # Also include as body for context
                "nsfw": "false",
                "spoiler": "false",
                "resubmit": "true",
            },
        )

        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "unknown")
            return self._failed_result(
                f"Reddit rate limit reached. "
                f"Retry after {retry_after} seconds."
            )

        if response.status_code not in {200, 201}:
            return self._failed_result(
                f"Reddit API error (HTTP {response.status_code})."
            )

        try:
            data = response.json()
        except Exception:
            return self._failed_result(
                "Reddit returned an unexpected non-JSON response."
            )

        # Navigate the nested JSON response structure
        json_data = data.get("json", {})
        errors: list = json_data.get("errors", [])

        if errors:
            # errors is a list of [field, message, modhash] triples
            readable_errors = "; ".join(
                e[1] if isinstance(e, (list, tuple)) and len(e) > 1 else str(e)
                for e in errors
            )
            return self._failed_result(
                f"Reddit submission error: {readable_errors}"
            )

        result_data = json_data.get("data", {})
        post_url: str | None = result_data.get("url")

        # Ensure URL is absolute
        if post_url and post_url.startswith("/"):
            post_url = f"{_REDDIT_BASE_URL}{post_url}"

        return self._success_result(
            posted_url=post_url,
            public_access=True,  # public subreddit posts are publicly visible
        )
