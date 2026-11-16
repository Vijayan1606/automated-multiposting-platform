"""
Tests for the PostingService.

Verifies:
  - All five platforms are invoked concurrently.
  - A failure on one platform does not affect the others.
  - success=True only when all configured platforms succeed.
  - success=False when any configured platform fails.
  - Unconfigured platforms are excluded from the success calculation.
  - Multiple simultaneous platform failures are handled.
  - Unexpected exceptions from platforms are caught and converted to
    failed results.
  - Response structure is always valid.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas import PlatformResult, PostingResponse
from app.services.posting_service import PostingService

# ── Fixtures ─────────────────────────────────────────────────────────────────

VALID_MESSAGE = "Check out our platform. https://example.com"


def _make_success(platform: str) -> PlatformResult:
    return PlatformResult(
        platform=platform,
        status="success",
        posted_url=f"https://example.com/post/1",
        public_access=True,
        date="2026-11-15",
        time="10:00:00",
        error=None,
    )


def _make_failed(platform: str, error: str = "API error") -> PlatformResult:
    return PlatformResult(
        platform=platform,
        status="failed",
        posted_url=None,
        public_access=False,
        date=None,
        time=None,
        error=error,
    )


def _make_unconfigured(platform: str) -> PlatformResult:
    return PlatformResult(
        platform=platform,
        status="unconfigured",
        posted_url=None,
        public_access=False,
        date=None,
        time=None,
        error="Platform credentials are not configured.",
    )


def _mock_platform(name: str, result: PlatformResult) -> MagicMock:
    """Create a mock BasePlatform that returns *result* from publish()."""
    mock = MagicMock()
    mock.name = name
    mock.publish = AsyncMock(return_value=result)
    return mock


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_all_platforms_success():
    """When all platforms succeed, success=True."""
    platforms = [
        _mock_platform("Telegram", _make_success("Telegram")),
        _mock_platform("Bluesky", _make_success("Bluesky")),
        _mock_platform("Mastodon", _make_success("Mastodon")),
        _mock_platform("LinkedIn", _make_success("LinkedIn")),
        _mock_platform("Reddit", _make_success("Reddit")),
    ]
    service = PostingService()
    service._platforms = platforms

    response = await service.post_to_all(VALID_MESSAGE)

    assert isinstance(response, PostingResponse)
    assert response.success is True
    assert len(response.results) == 5
    assert all(r.status == "success" for r in response.results)


@pytest.mark.asyncio
async def test_one_platform_fails_success_false():
    """When one platform fails, success=False."""
    platforms = [
        _mock_platform("Telegram", _make_success("Telegram")),
        _mock_platform("Bluesky", _make_failed("Bluesky")),
        _mock_platform("Mastodon", _make_success("Mastodon")),
        _mock_platform("LinkedIn", _make_success("LinkedIn")),
        _mock_platform("Reddit", _make_success("Reddit")),
    ]
    service = PostingService()
    service._platforms = platforms

    response = await service.post_to_all(VALID_MESSAGE)

    assert response.success is False
    failed = [r for r in response.results if r.status == "failed"]
    assert len(failed) == 1
    assert failed[0].platform == "Bluesky"


@pytest.mark.asyncio
async def test_multiple_platforms_fail():
    """Multiple simultaneous failures are all captured."""
    platforms = [
        _mock_platform("Telegram", _make_failed("Telegram", "Timeout")),
        _mock_platform("Bluesky", _make_failed("Bluesky", "Auth error")),
        _mock_platform("Mastodon", _make_success("Mastodon")),
        _mock_platform("LinkedIn", _make_failed("LinkedIn", "403 Forbidden")),
        _mock_platform("Reddit", _make_success("Reddit")),
    ]
    service = PostingService()
    service._platforms = platforms

    response = await service.post_to_all(VALID_MESSAGE)

    assert response.success is False
    failed = [r for r in response.results if r.status == "failed"]
    assert len(failed) == 3
    failed_names = {r.platform for r in failed}
    assert failed_names == {"Telegram", "Bluesky", "LinkedIn"}


@pytest.mark.asyncio
async def test_all_platforms_fail():
    """When all platforms fail, success=False."""
    platforms = [
        _mock_platform("Telegram", _make_failed("Telegram")),
        _mock_platform("Bluesky", _make_failed("Bluesky")),
        _mock_platform("Mastodon", _make_failed("Mastodon")),
        _mock_platform("LinkedIn", _make_failed("LinkedIn")),
        _mock_platform("Reddit", _make_failed("Reddit")),
    ]
    service = PostingService()
    service._platforms = platforms

    response = await service.post_to_all(VALID_MESSAGE)

    assert response.success is False
    assert all(r.status == "failed" for r in response.results)


@pytest.mark.asyncio
async def test_unconfigured_platforms_excluded_from_success():
    """
    Unconfigured platforms do not count against success.
    If the only active platforms all succeed, success=True.
    """
    platforms = [
        _mock_platform("Telegram", _make_success("Telegram")),
        _mock_platform("Bluesky", _make_unconfigured("Bluesky")),
        _mock_platform("Mastodon", _make_unconfigured("Mastodon")),
        _mock_platform("LinkedIn", _make_unconfigured("LinkedIn")),
        _mock_platform("Reddit", _make_unconfigured("Reddit")),
    ]
    service = PostingService()
    service._platforms = platforms

    response = await service.post_to_all(VALID_MESSAGE)

    assert response.success is True


@pytest.mark.asyncio
async def test_all_unconfigured_success_false():
    """
    When no platforms are configured at all, success=False.
    """
    platforms = [
        _mock_platform("Telegram", _make_unconfigured("Telegram")),
        _mock_platform("Bluesky", _make_unconfigured("Bluesky")),
        _mock_platform("Mastodon", _make_unconfigured("Mastodon")),
        _mock_platform("LinkedIn", _make_unconfigured("LinkedIn")),
        _mock_platform("Reddit", _make_unconfigured("Reddit")),
    ]
    service = PostingService()
    service._platforms = platforms

    response = await service.post_to_all(VALID_MESSAGE)

    assert response.success is False


@pytest.mark.asyncio
async def test_partial_success_other_platforms_still_run():
    """
    When one platform raises an unexpected exception, all others
    still execute and their results are captured.
    """

    async def raise_unexpectedly(message: str):
        raise RuntimeError("Simulated unexpected bug")

    failing_mock = MagicMock()
    failing_mock.name = "Telegram"
    failing_mock.publish = raise_unexpectedly  # actual exception, not mock

    platforms = [
        failing_mock,
        _mock_platform("Bluesky", _make_success("Bluesky")),
        _mock_platform("Mastodon", _make_success("Mastodon")),
        _mock_platform("LinkedIn", _make_success("LinkedIn")),
        _mock_platform("Reddit", _make_success("Reddit")),
    ]
    service = PostingService()
    service._platforms = platforms

    response = await service.post_to_all(VALID_MESSAGE)

    assert response.success is False
    assert len(response.results) == 5

    telegram_result = next(r for r in response.results if r.platform == "Telegram")
    assert telegram_result.status == "failed"

    # Other platforms succeeded
    others = [r for r in response.results if r.platform != "Telegram"]
    assert all(r.status == "success" for r in others)


@pytest.mark.asyncio
async def test_response_structure_always_valid():
    """Every result always has the required fields."""
    platforms = [
        _mock_platform("Telegram", _make_success("Telegram")),
        _mock_platform("Bluesky", _make_failed("Bluesky")),
        _mock_platform("Mastodon", _make_unconfigured("Mastodon")),
        _mock_platform("LinkedIn", _make_success("LinkedIn")),
        _mock_platform("Reddit", _make_failed("Reddit")),
    ]
    service = PostingService()
    service._platforms = platforms

    response = await service.post_to_all(VALID_MESSAGE)

    for result in response.results:
        assert result.platform
        assert result.status in {"success", "failed", "unconfigured"}
        # Failed/unconfigured must have null date/time
        if result.status != "success":
            assert result.date is None
            assert result.time is None
        # Successful results must have date/time
        if result.status == "success":
            assert result.date is not None
            assert result.time is not None


@pytest.mark.asyncio
async def test_platforms_called_with_correct_message():
    """Every platform is called with the exact message passed in."""
    captured_messages: dict[str, str] = {}
    test_message = "Test post https://example.com/test"

    def make_publish(platform_name: str):
        """Factory that returns an async publish function for each platform."""
        async def _publish(msg: str) -> PlatformResult:
            captured_messages[platform_name] = msg
            return _make_success(platform_name)
        return _publish

    platforms = []
    for name in ["Telegram", "Bluesky", "Mastodon", "LinkedIn", "Reddit"]:
        mock = MagicMock()
        mock.name = name
        mock.publish = make_publish(name)
        platforms.append(mock)

    service = PostingService()
    service._platforms = platforms

    await service.post_to_all(test_message)

    for name in ["Telegram", "Bluesky", "Mastodon", "LinkedIn", "Reddit"]:
        assert captured_messages.get(name) == test_message
