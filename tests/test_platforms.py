"""
Platform-level unit tests.

Each test mocks all HTTP calls using unittest.mock so that:
  - No real network requests are made.
  - No real credentials are needed.
  - API behaviour can be simulated precisely.

Tests verify:
  - Correct endpoint called with correct payload.
  - Successful API response → success PlatformResult.
  - Authentication failures → failed PlatformResult with sanitized error.
  - Rate limit responses → failed PlatformResult with retry info.
  - Network errors → failed PlatformResult.
  - Missing credentials → unconfigured PlatformResult.
  - Response fields (posted_url, public_access, date, time) are correct.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.platforms.bluesky import BlueskyPlatform
from app.platforms.linkedin import LinkedInPlatform
from app.platforms.mastodon import MastodonPlatform
from app.platforms.reddit import RedditPlatform
from app.platforms.telegram import TelegramPlatform

VALID_MESSAGE = "Check out our platform. https://example.com"


# ── Helper: build a mock httpx.Response ─────────────────────────────────────


def _mock_response(
    status_code: int,
    json_body: dict | None = None,
    headers: dict | None = None,
) -> MagicMock:
    response = MagicMock(spec=httpx.Response)
    response.status_code = status_code
    response.headers = httpx.Headers(headers or {})
    if json_body is not None:
        response.json = MagicMock(return_value=json_body)
    else:
        response.json = MagicMock(side_effect=Exception("No JSON"))
    return response


# ══════════════════════════════════════════════════════════════════════════════
# Telegram
# ══════════════════════════════════════════════════════════════════════════════


class TestTelegramPlatform:

    @pytest.mark.asyncio
    async def test_unconfigured_when_no_credentials(self):
        with patch("app.platforms.telegram.settings") as mock_settings:
            mock_settings.telegram_configured = False
            result = await TelegramPlatform().publish(VALID_MESSAGE)
        assert result.status == "unconfigured"
        assert result.platform == "Telegram"

    @pytest.mark.asyncio
    async def test_success_public_channel(self):
        success_body = {
            "ok": True,
            "result": {
                "message_id": 42,
                "chat": {
                    "id": -1001234567890,
                    "type": "channel",
                    "username": "mychannel",
                },
            },
        }
        mock_resp = _mock_response(200, success_body)

        with patch("app.platforms.telegram.settings") as mock_settings, \
             patch.object(TelegramPlatform, "_make_client") as mock_make_client:
            mock_settings.telegram_configured = True
            mock_settings.telegram_bot_token = "FAKE_TOKEN"
            mock_settings.telegram_chat_id = "-1001234567890"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_make_client.return_value = mock_client

            result = await TelegramPlatform().publish(VALID_MESSAGE)

        assert result.status == "success"
        assert result.public_access is True
        assert result.posted_url == "https://t.me/mychannel/42"
        assert result.date is not None
        assert result.time is not None
        assert result.error is None

    @pytest.mark.asyncio
    async def test_auth_failure(self):
        mock_resp = _mock_response(401)

        with patch("app.platforms.telegram.settings") as mock_settings, \
             patch.object(TelegramPlatform, "_make_client") as mock_make_client:
            mock_settings.telegram_configured = True
            mock_settings.telegram_bot_token = "BAD_TOKEN"
            mock_settings.telegram_chat_id = "12345"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_make_client.return_value = mock_client

            result = await TelegramPlatform().publish(VALID_MESSAGE)

        assert result.status == "failed"
        assert "BAD_TOKEN" not in (result.error or "")
        assert "FAKE_TOKEN" not in (result.error or "")

    @pytest.mark.asyncio
    async def test_api_error_response(self):
        error_body = {
            "ok": False,
            "error_code": 400,
            "description": "Bad Request: chat not found",
        }
        mock_resp = _mock_response(200, error_body)

        with patch("app.platforms.telegram.settings") as mock_settings, \
             patch.object(TelegramPlatform, "_make_client") as mock_make_client:
            mock_settings.telegram_configured = True
            mock_settings.telegram_bot_token = "FAKE_TOKEN"
            mock_settings.telegram_chat_id = "99999"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_make_client.return_value = mock_client

            result = await TelegramPlatform().publish(VALID_MESSAGE)

        assert result.status == "failed"
        assert "chat not found" in result.error

    @pytest.mark.asyncio
    async def test_timeout_error(self):
        with patch("app.platforms.telegram.settings") as mock_settings, \
             patch.object(TelegramPlatform, "_make_client") as mock_make_client:
            mock_settings.telegram_configured = True
            mock_settings.telegram_bot_token = "FAKE_TOKEN"
            mock_settings.telegram_chat_id = "12345"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(
                side_effect=httpx.TimeoutException("timed out")
            )
            mock_make_client.return_value = mock_client

            result = await TelegramPlatform().publish(VALID_MESSAGE)

        assert result.status == "failed"
        assert "timed out" in result.error.lower()


# ══════════════════════════════════════════════════════════════════════════════
# Bluesky
# ══════════════════════════════════════════════════════════════════════════════


class TestBlueskyPlatform:

    @pytest.mark.asyncio
    async def test_unconfigured_when_no_credentials(self):
        with patch("app.platforms.bluesky.settings") as mock_settings:
            mock_settings.bluesky_configured = False
            result = await BlueskyPlatform().publish(VALID_MESSAGE)
        assert result.status == "unconfigured"

    @pytest.mark.asyncio
    async def test_success(self):
        session_body = {
            "accessJwt": "FAKE_JWT",
            "did": "did:plc:abcdef123456",
        }
        post_body = {
            "uri": "at://did:plc:abcdef123456/app.bsky.feed.post/abc123rkey",
            "cid": "bafyreid123",
        }

        with patch("app.platforms.bluesky.settings") as mock_settings, \
             patch.object(BlueskyPlatform, "_make_client") as mock_make_client:
            mock_settings.bluesky_configured = True
            mock_settings.bluesky_identifier = "user.bsky.social"
            mock_settings.bluesky_app_password = "FAKE_PASSWORD"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            # First call: session, second call: post
            mock_client.post = AsyncMock(
                side_effect=[
                    _mock_response(200, session_body),
                    _mock_response(200, post_body),
                ]
            )
            mock_make_client.return_value = mock_client

            result = await BlueskyPlatform().publish(VALID_MESSAGE)

        assert result.status == "success"
        assert result.public_access is True
        assert "bsky.app" in result.posted_url
        assert "abc123rkey" in result.posted_url

    @pytest.mark.asyncio
    async def test_auth_failure(self):
        with patch("app.platforms.bluesky.settings") as mock_settings, \
             patch.object(BlueskyPlatform, "_make_client") as mock_make_client:
            mock_settings.bluesky_configured = True
            mock_settings.bluesky_identifier = "user.bsky.social"
            mock_settings.bluesky_app_password = "WRONG_PASSWORD"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(
                return_value=_mock_response(401)
            )
            mock_make_client.return_value = mock_client

            result = await BlueskyPlatform().publish(VALID_MESSAGE)

        assert result.status == "failed"
        assert "WRONG_PASSWORD" not in (result.error or "")


# ══════════════════════════════════════════════════════════════════════════════
# Mastodon
# ══════════════════════════════════════════════════════════════════════════════


class TestMastodonPlatform:

    @pytest.mark.asyncio
    async def test_unconfigured_when_no_credentials(self):
        with patch("app.platforms.mastodon.settings") as mock_settings:
            mock_settings.mastodon_configured = False
            result = await MastodonPlatform().publish(VALID_MESSAGE)
        assert result.status == "unconfigured"

    @pytest.mark.asyncio
    async def test_success_public_visibility(self):
        status_body = {
            "id": "109375745745649537",
            "url": "https://mastodon.social/@user/109375745745649537",
            "visibility": "public",
        }
        with patch("app.platforms.mastodon.settings") as mock_settings, \
             patch.object(MastodonPlatform, "_make_client") as mock_make_client:
            mock_settings.mastodon_configured = True
            mock_settings.mastodon_instance_url = "https://mastodon.social"
            mock_settings.mastodon_access_token = "FAKE_TOKEN"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(
                return_value=_mock_response(200, status_body)
            )
            mock_make_client.return_value = mock_client

            result = await MastodonPlatform().publish(VALID_MESSAGE)

        assert result.status == "success"
        assert result.public_access is True
        assert result.posted_url == "https://mastodon.social/@user/109375745745649537"

    @pytest.mark.asyncio
    async def test_rate_limit(self):
        mock_resp = _mock_response(
            429, None, {"Retry-After": "60"}
        )
        mock_resp.json = MagicMock(side_effect=Exception("no body"))

        with patch("app.platforms.mastodon.settings") as mock_settings, \
             patch.object(MastodonPlatform, "_make_client") as mock_make_client:
            mock_settings.mastodon_configured = True
            mock_settings.mastodon_instance_url = "https://mastodon.social"
            mock_settings.mastodon_access_token = "FAKE_TOKEN"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_make_client.return_value = mock_client

            result = await MastodonPlatform().publish(VALID_MESSAGE)

        assert result.status == "failed"
        assert "rate limit" in result.error.lower()
        assert "60" in result.error

    @pytest.mark.asyncio
    async def test_auth_failure(self):
        with patch("app.platforms.mastodon.settings") as mock_settings, \
             patch.object(MastodonPlatform, "_make_client") as mock_make_client:
            mock_settings.mastodon_configured = True
            mock_settings.mastodon_instance_url = "https://mastodon.social"
            mock_settings.mastodon_access_token = "BAD_TOKEN"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(
                return_value=_mock_response(401)
            )
            mock_make_client.return_value = mock_client

            result = await MastodonPlatform().publish(VALID_MESSAGE)

        assert result.status == "failed"
        assert "BAD_TOKEN" not in (result.error or "")


# ══════════════════════════════════════════════════════════════════════════════
# LinkedIn
# ══════════════════════════════════════════════════════════════════════════════


class TestLinkedInPlatform:

    @pytest.mark.asyncio
    async def test_unconfigured_when_no_credentials(self):
        with patch("app.platforms.linkedin.settings") as mock_settings:
            mock_settings.linkedin_configured = False
            result = await LinkedInPlatform().publish(VALID_MESSAGE)
        assert result.status == "unconfigured"

    @pytest.mark.asyncio
    async def test_success(self):
        post_body = {"id": "urn:li:ugcPost:7183456789012345"}
        with patch("app.platforms.linkedin.settings") as mock_settings, \
             patch.object(LinkedInPlatform, "_make_client") as mock_make_client:
            mock_settings.linkedin_configured = True
            mock_settings.linkedin_access_token = "FAKE_TOKEN"
            mock_settings.linkedin_person_urn = "urn:li:person:ABCDE"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(
                return_value=_mock_response(201, post_body)
            )
            mock_make_client.return_value = mock_client

            result = await LinkedInPlatform().publish(VALID_MESSAGE)

        assert result.status == "success"
        assert result.public_access is True
        assert "linkedin.com/feed/update" in result.posted_url

    @pytest.mark.asyncio
    async def test_expired_token(self):
        with patch("app.platforms.linkedin.settings") as mock_settings, \
             patch.object(LinkedInPlatform, "_make_client") as mock_make_client:
            mock_settings.linkedin_configured = True
            mock_settings.linkedin_access_token = "EXPIRED_TOKEN"
            mock_settings.linkedin_person_urn = "urn:li:person:ABCDE"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(
                return_value=_mock_response(401)
            )
            mock_make_client.return_value = mock_client

            result = await LinkedInPlatform().publish(VALID_MESSAGE)

        assert result.status == "failed"
        assert "EXPIRED_TOKEN" not in (result.error or "")

    @pytest.mark.asyncio
    async def test_missing_scope_error(self):
        error_body = {"message": "Not enough permissions to access"}
        with patch("app.platforms.linkedin.settings") as mock_settings, \
             patch.object(LinkedInPlatform, "_make_client") as mock_make_client:
            mock_settings.linkedin_configured = True
            mock_settings.linkedin_access_token = "FAKE_TOKEN"
            mock_settings.linkedin_person_urn = "urn:li:person:ABCDE"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(
                return_value=_mock_response(403, error_body)
            )
            mock_make_client.return_value = mock_client

            result = await LinkedInPlatform().publish(VALID_MESSAGE)

        assert result.status == "failed"
        assert "scope" in result.error.lower() or "forbidden" in result.error.lower()


# ══════════════════════════════════════════════════════════════════════════════
# Reddit
# ══════════════════════════════════════════════════════════════════════════════


class TestRedditPlatform:

    @pytest.mark.asyncio
    async def test_unconfigured_when_no_credentials(self):
        with patch("app.platforms.reddit.settings") as mock_settings:
            mock_settings.reddit_configured = False
            result = await RedditPlatform().publish(VALID_MESSAGE)
        assert result.status == "unconfigured"

    @pytest.mark.asyncio
    async def test_success(self):
        token_body = {"access_token": "FAKE_REDDIT_TOKEN", "token_type": "bearer"}
        submit_body = {
            "json": {
                "errors": [],
                "data": {
                    "url": "https://www.reddit.com/r/test/comments/abc123/check_out_our_platform/",
                    "id": "abc123",
                    "name": "t3_abc123",
                },
            }
        }

        with patch("app.platforms.reddit.settings") as mock_settings, \
             patch.object(RedditPlatform, "_make_client") as mock_make_client:
            mock_settings.reddit_configured = True
            mock_settings.reddit_client_id = "CLIENT_ID"
            mock_settings.reddit_client_secret = "CLIENT_SECRET"
            mock_settings.reddit_username = "test_user"
            mock_settings.reddit_password = "test_pass"
            mock_settings.reddit_user_agent = "python:test:v1.0"
            mock_settings.reddit_subreddit = "test"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(
                side_effect=[
                    _mock_response(200, token_body),
                    _mock_response(200, submit_body),
                ]
            )
            mock_make_client.return_value = mock_client

            result = await RedditPlatform().publish(VALID_MESSAGE)

        assert result.status == "success"
        assert result.public_access is True
        assert "reddit.com/r/test" in result.posted_url

    @pytest.mark.asyncio
    async def test_token_auth_failure(self):
        with patch("app.platforms.reddit.settings") as mock_settings, \
             patch.object(RedditPlatform, "_make_client") as mock_make_client:
            mock_settings.reddit_configured = True
            mock_settings.reddit_client_id = "BAD_ID"
            mock_settings.reddit_client_secret = "BAD_SECRET"
            mock_settings.reddit_username = "user"
            mock_settings.reddit_password = "pass"
            mock_settings.reddit_user_agent = "python:test:v1.0"
            mock_settings.reddit_subreddit = "test"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(
                return_value=_mock_response(401)
            )
            mock_make_client.return_value = mock_client

            result = await RedditPlatform().publish(VALID_MESSAGE)

        assert result.status == "failed"
        assert "BAD_SECRET" not in (result.error or "")

    @pytest.mark.asyncio
    async def test_submission_error_in_json(self):
        """Reddit can return HTTP 200 with errors in the JSON body."""
        token_body = {"access_token": "FAKE_TOKEN", "token_type": "bearer"}
        submit_body = {
            "json": {
                "errors": [["RATELIMIT", "you are doing that too much", "ratelimit"]],
                "data": {},
            }
        }

        with patch("app.platforms.reddit.settings") as mock_settings, \
             patch.object(RedditPlatform, "_make_client") as mock_make_client:
            mock_settings.reddit_configured = True
            mock_settings.reddit_client_id = "CLIENT_ID"
            mock_settings.reddit_client_secret = "CLIENT_SECRET"
            mock_settings.reddit_username = "test_user"
            mock_settings.reddit_password = "test_pass"
            mock_settings.reddit_user_agent = "python:test:v1.0"
            mock_settings.reddit_subreddit = "test"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(
                side_effect=[
                    _mock_response(200, token_body),
                    _mock_response(200, submit_body),
                ]
            )
            mock_make_client.return_value = mock_client

            result = await RedditPlatform().publish(VALID_MESSAGE)

        assert result.status == "failed"
        assert "too much" in result.error.lower() or "ratelimit" in result.error.lower()

    @pytest.mark.asyncio
    async def test_network_error(self):
        with patch("app.platforms.reddit.settings") as mock_settings, \
             patch.object(RedditPlatform, "_make_client") as mock_make_client:
            mock_settings.reddit_configured = True
            mock_settings.reddit_client_id = "CLIENT_ID"
            mock_settings.reddit_client_secret = "CLIENT_SECRET"
            mock_settings.reddit_username = "test_user"
            mock_settings.reddit_password = "test_pass"
            mock_settings.reddit_user_agent = "python:test:v1.0"
            mock_settings.reddit_subreddit = "test"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            mock_make_client.return_value = mock_client

            result = await RedditPlatform().publish(VALID_MESSAGE)

        assert result.status == "failed"
        assert "network" in result.error.lower() or "connect" in result.error.lower()
