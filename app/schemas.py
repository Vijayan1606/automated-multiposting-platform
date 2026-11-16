"""
Pydantic request and response schemas.

This module defines:
  - MessageRequest   – incoming POST /posting payload with full validation
  - PlatformResult   – per-platform publishing outcome
  - PostingResponse  – top-level API response

URL validation rules (enforced in MessageRequest):
  1. Message must not be empty.
  2. Message must not exceed 200 characters.
  3. Message must contain exactly ONE URL.
  4. The URL must be valid and use http or https scheme only.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# URL detection helpers
# ---------------------------------------------------------------------------

# Regex that finds URL-like tokens in text.
# Uses word boundary anchors and common URL patterns to avoid matching
# plain punctuation or fragments inside words.
_URL_PATTERN = re.compile(
    r"(?i)\b(?:https?|ftp)://[^\s<>\"\'\]\[(){},;]+",
    re.IGNORECASE,
)

# A looser pattern to detect any potential URL-like tokens (including
# bare domains without scheme) so we can warn the user appropriately.
_BARE_DOMAIN_PATTERN = re.compile(
    r"(?<!\S)(?:www\.)[^\s<>\"\'\]\[(){},;]+",
    re.IGNORECASE,
)


def _extract_urls(text: str) -> list[str]:
    """
    Extract all schemed URL candidates from *text*.

    Strips trailing punctuation characters that may have been captured
    by the regex but are not part of the URL (e.g. trailing periods,
    commas, closing parentheses).
    """
    raw_matches = _URL_PATTERN.findall(text)
    cleaned: list[str] = []
    for url in raw_matches:
        # Strip common trailing punctuation not part of valid URLs
        url = url.rstrip(".,;:!?)>\"'")
        cleaned.append(url)
    return cleaned


def _is_valid_http_url(url: str) -> bool:
    """
    Return True when *url* is a well-formed HTTP or HTTPS URL.

    Checks:
    - Scheme is http or https (case-insensitive).
    - Network location (host) is non-empty.
    - Path is well-formed (urlparse succeeds without raising).
    """
    try:
        parsed = urlparse(url)
        return (
            parsed.scheme.lower() in {"http", "https"}
            and bool(parsed.netloc)
            # netloc must contain at least one dot or be a valid hostname
            and "." in parsed.netloc
        )
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Request schema
# ---------------------------------------------------------------------------


class MessageRequest(BaseModel):
    """
    Payload for POST /posting.

    Validation rules (applied in order):
      1. message must not be empty or whitespace-only.
      2. message must not exceed 200 characters.
      3. message must contain exactly one URL.
      4. The URL must use http or https scheme.
      5. The URL must be syntactically valid.
    """

    message: str = Field(
        ...,
        description=(
            "The message to publish. Must be 1–200 characters, contain "
            "exactly one valid HTTP/HTTPS CTA URL, and no other URLs."
        ),
        examples=[
            "Check out our latest platform and grow your visibility. "
            "https://example.com"
        ],
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        # 1. Reject blank / whitespace-only messages
        stripped = value.strip()
        if not stripped:
            raise ValueError("Message must not be empty.")

        # 2. Enforce maximum length on the original value (not stripped)
        if len(value) > 200:
            raise ValueError(
                f"Message must not exceed 200 characters "
                f"(received {len(value)})."
            )

        # 3. Extract schemed URLs
        urls = _extract_urls(value)

        if len(urls) == 0:
            raise ValueError(
                "Message must contain exactly one CTA URL "
                "(http:// or https://). No URL was found."
            )

        if len(urls) > 1:
            raise ValueError(
                f"Message must contain exactly one CTA URL, "
                f"but {len(urls)} URLs were found: {', '.join(urls)}"
            )

        url = urls[0]

        # 4. Reject non-http/https schemes
        try:
            scheme = urlparse(url).scheme.lower()
        except Exception:
            scheme = ""

        if scheme not in {"http", "https"}:
            raise ValueError(
                f"Only http and https URLs are accepted. "
                f"Found scheme: '{scheme or 'unknown'}'."
            )

        # 5. Validate URL structure
        if not _is_valid_http_url(url):
            raise ValueError(
                f"The URL '{url}' is malformed or missing a valid host."
            )

        return value


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class PlatformResult(BaseModel):
    """Outcome of a single platform publishing attempt."""

    platform: str = Field(description="Name of the social platform.")
    status: Literal["success", "failed", "unconfigured"] = Field(
        description=(
            "'success' – published successfully; "
            "'failed' – attempted but failed; "
            "'unconfigured' – missing credentials, not attempted."
        )
    )
    posted_url: str | None = Field(
        default=None,
        description="Public URL of the published post, if available.",
    )
    public_access: bool = Field(
        default=False,
        description="True when the post is publicly accessible.",
    )
    date: str | None = Field(
        default=None,
        description="Date the post was published (YYYY-MM-DD).",
    )
    time: str | None = Field(
        default=None,
        description="Time the post was published (HH:MM:SS).",
    )
    error: str | None = Field(
        default=None,
        description="Human-readable error message on failure.",
    )


class PostingResponse(BaseModel):
    """Top-level response returned by POST /posting."""

    success: bool = Field(
        description=(
            "True only when every configured platform published successfully. "
            "False if any configured platform failed or if no platform "
            "is configured."
        )
    )
    results: list[PlatformResult] = Field(
        description="Per-platform publishing outcomes."
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "success": True,
                    "results": [
                        {
                            "platform": "Telegram",
                            "status": "success",
                            "posted_url": "https://t.me/c/123456789/42",
                            "public_access": False,
                            "date": "2026-11-15",
                            "time": "10:30:00",
                            "error": None,
                        },
                        {
                            "platform": "Bluesky",
                            "status": "failed",
                            "posted_url": None,
                            "public_access": False,
                            "date": None,
                            "time": None,
                            "error": "Authentication failed",
                        },
                    ],
                }
            ]
        }
    }
