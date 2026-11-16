"""
Tests for message and URL validation (Pydantic schema layer).

Covers all 10 validation scenarios from the assignment spec:
  1.  Valid message with one URL.
  2.  Empty message.
  3.  Message exceeding 200 characters.
  4.  Message without a URL.
  5.  Message containing two URLs.
  6.  Invalid URL (bad host).
  7.  FTP URL.
  8.  URL with malformed syntax (no host).
  9.  Message with leading/trailing whitespace only.
  10. Message containing a URL with query parameters.

Additional edge cases:
  - URL with path and fragment.
  - Text ending with a period (should not be counted as extra URL chars).
  - Exactly 200-character message.
  - 201-character message (rejected).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

import app.main as main_module
from app.main import app
from app.schemas import MessageRequest, PostingResponse, PlatformResult
from app.services.posting_service import PostingService

# Use TestClient with raise_server_exceptions=True (default) so errors surface
client = TestClient(app)


# ── Helper to call the endpoint ─────────────────────────────────────────────

def _post(message: str):
    """
    POST /posting with a mock posting service that immediately returns.

    Because the FastAPI lifespan is not triggered by TestClient by default,
    _posting_service may be None. We inject a mock service directly into
    the module before the request and restore it after.
    """
    mock_response = PostingResponse(
        success=True,
        results=[
            PlatformResult(
                platform="Telegram",
                status="success",
                posted_url="https://t.me/testchannel/1",
                public_access=True,
                date="2026-11-15",
                time="10:00:00",
                error=None,
            )
        ],
    )
    mock_service = MagicMock(spec=PostingService)
    mock_service.post_to_all = AsyncMock(return_value=mock_response)

    original = main_module._posting_service
    main_module._posting_service = mock_service
    try:
        return client.post("/posting", json={"message": message})
    finally:
        main_module._posting_service = original


# ── Schema-level unit tests (no HTTP overhead) ───────────────────────────────


class TestMessageRequestSchema:
    """Unit tests directly validating the Pydantic schema."""

    def test_valid_message_with_url(self):
        """Scenario 1: Valid message with one URL passes validation."""
        req = MessageRequest(
            message="Check out our platform. https://example.com"
        )
        assert req.message == "Check out our platform. https://example.com"

    def test_empty_message_rejected(self):
        """Scenario 2: Empty string is rejected."""
        with pytest.raises(Exception, match="empty"):
            MessageRequest(message="")

    def test_whitespace_only_message_rejected(self):
        """Scenario 9: Whitespace-only message is rejected as empty."""
        with pytest.raises(Exception, match="empty"):
            MessageRequest(message="   ")

    def test_message_too_long_rejected(self):
        """Scenario 3: Message exceeding 200 characters is rejected."""
        long_msg = "A" * 170 + " https://example.com " + "B" * 20
        assert len(long_msg) > 200
        with pytest.raises(Exception, match="200"):
            MessageRequest(message=long_msg)

    def test_exactly_200_chars_accepted(self):
        """Boundary: exactly 200 characters is accepted."""
        # Build a message that is exactly 200 chars with one URL
        url = "https://example.com"
        padding = "A" * (200 - len(url) - 1)
        msg = padding + " " + url
        assert len(msg) == 200
        req = MessageRequest(message=msg)
        assert req.message == msg

    def test_201_chars_rejected(self):
        """Boundary: 201 characters is rejected."""
        url = "https://example.com"
        padding = "A" * (201 - len(url) - 1)
        msg = padding + " " + url
        assert len(msg) == 201
        with pytest.raises(Exception, match="200"):
            MessageRequest(message=msg)

    def test_no_url_rejected(self):
        """Scenario 4: Message without any URL is rejected."""
        with pytest.raises(Exception, match="URL"):
            MessageRequest(message="This message has no URL at all.")

    def test_two_urls_rejected(self):
        """Scenario 5: Message with two URLs is rejected."""
        with pytest.raises(Exception, match="2 URLs"):
            MessageRequest(
                message=(
                    "Visit https://example.com and also https://other.com"
                )
            )

    def test_invalid_url_rejected(self):
        """Scenario 6: URL with invalid host (no dot) is rejected."""
        with pytest.raises(Exception):
            MessageRequest(message="Check this out: https://invalid")

    def test_ftp_url_rejected(self):
        """Scenario 7: FTP URL scheme is rejected."""
        with pytest.raises(Exception, match="https"):
            MessageRequest(
                message="Download from ftp://files.example.com/resource"
            )

    def test_malformed_url_rejected(self):
        """Scenario 8: URL with no host component is rejected."""
        with pytest.raises(Exception):
            MessageRequest(message="See https:// for details.")

    def test_url_with_query_params_accepted(self):
        """Scenario 10: URL with query parameters is valid."""
        req = MessageRequest(
            message=(
                "Track your campaign: "
                "https://example.com/page?utm_source=social&ref=post"
            )
        )
        assert "utm_source" in req.message

    def test_url_with_path_and_fragment(self):
        """URL with path and fragment is accepted."""
        req = MessageRequest(
            message="Learn more: https://docs.example.com/guide#section-1"
        )
        assert req.message

    def test_trailing_period_not_counted_as_url(self):
        """
        A URL followed by a period should not cause 'multiple URLs' error.
        The trailing period must be stripped from the URL candidate.
        """
        req = MessageRequest(
            message="Check out https://example.com. Great platform!"
        )
        assert req.message

    def test_url_at_start_of_message(self):
        """URL at the beginning of the message is valid."""
        req = MessageRequest(
            message="https://example.com – our new platform. Join us!"
        )
        assert req.message

    def test_https_url_accepted(self):
        """HTTPS scheme is explicitly accepted."""
        req = MessageRequest(
            message="Secure link: https://secure.example.com/page"
        )
        assert req.message

    def test_http_url_accepted(self):
        """HTTP scheme is also accepted."""
        req = MessageRequest(
            message="Visit our site: http://example.com/landing"
        )
        assert req.message


# ── API endpoint tests ───────────────────────────────────────────────────────


class TestPostingEndpoint:
    """Integration tests for the POST /posting endpoint."""

    def test_valid_request_returns_200(self):
        """Valid message returns HTTP 200."""
        response = _post(
            "Check out our latest platform. https://example.com"
        )
        assert response.status_code == 200

    def test_valid_request_response_structure(self):
        """Valid message returns correct top-level response structure."""
        response = _post(
            "Check out our latest platform. https://example.com"
        )
        data = response.json()
        assert "success" in data
        assert "results" in data
        assert isinstance(data["results"], list)

    def test_empty_message_returns_422(self):
        """Empty message returns 422 Unprocessable Entity."""
        response = client.post("/posting", json={"message": ""})
        assert response.status_code == 422

    def test_message_too_long_returns_422(self):
        """Message over 200 chars returns 422."""
        response = client.post(
            "/posting",
            json={"message": "A" * 180 + " https://example.com " + "B" * 20},
        )
        assert response.status_code == 422

    def test_no_url_returns_422(self):
        """Message without URL returns 422."""
        response = client.post(
            "/posting", json={"message": "No URL in this message."}
        )
        assert response.status_code == 422

    def test_two_urls_returns_422(self):
        """Message with two URLs returns 422."""
        response = client.post(
            "/posting",
            json={
                "message": (
                    "See https://example.com and https://other.com"
                )
            },
        )
        assert response.status_code == 422

    def test_ftp_url_returns_422(self):
        """FTP URL returns 422."""
        response = client.post(
            "/posting",
            json={"message": "Get it from ftp://files.example.com/file"},
        )
        assert response.status_code == 422

    def test_missing_message_field_returns_422(self):
        """Missing 'message' field returns 422."""
        response = client.post("/posting", json={})
        assert response.status_code == 422

    def test_non_json_body_returns_422(self):
        """Non-JSON body returns 422."""
        response = client.post(
            "/posting",
            content="plain text",
            headers={"Content-Type": "text/plain"},
        )
        assert response.status_code == 422

    def test_422_response_has_detail_field(self):
        """422 response includes a 'detail' field."""
        response = client.post("/posting", json={"message": ""})
        data = response.json()
        assert "detail" in data

    def test_health_endpoint(self):
        """Health check returns 200 with status ok."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
