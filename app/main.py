"""
FastAPI application entry point.

Exposes:
  POST /posting   – publish a message to all configured platforms
  GET  /health    – simple health-check endpoint
  GET  /docs      – Swagger UI (FastAPI default)
  GET  /redoc     – ReDoc UI (FastAPI default)

Design decisions:
  - PostingService is instantiated once at startup using a FastAPI
    lifespan context manager (preferred over @app.on_event in FastAPI 0.95+).
  - Pydantic RequestValidationError is caught globally to return a
    consistent 422 JSON error body matching the project's error style.
  - API key / token values are never echoed in logs or responses.
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import settings
from app.schemas import MessageRequest, PostingResponse
from app.services.posting_service import PostingService

# ── Logging configuration ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ── Application state ───────────────────────────────────────────────────────
_posting_service: PostingService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.

    Initialises the PostingService on startup and cleans up on shutdown.
    """
    global _posting_service
    logger.info("Starting %s v%s", settings.app_title, settings.app_version)
    _posting_service = PostingService()
    logger.info("PostingService initialised with %d platforms.", 5)
    yield
    logger.info("Shutting down %s.", settings.app_title)
    _posting_service = None


# ── FastAPI instance ────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_title,
    version=settings.app_version,
    description=(
        "An automated multi-platform social media posting system.\n\n"
        "Send a single POST request with a message containing exactly one "
        "CTA URL and the system will concurrently publish it to Telegram, "
        "Bluesky, Mastodon, LinkedIn, and Reddit.\n\n"
        "**Key features:**\n"
        "- Strict message and URL validation\n"
        "- Concurrent publishing via asyncio\n"
        "- Independent per-platform error handling\n"
        "- Standardised JSON response with per-platform results\n"
    ),
    contact={
        "name": "Dxora Technologies – Technical Assignment",
    },
    license_info={
        "name": "MIT",
    },
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ── Global exception handlers ────────────────────────────────────────────────


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Return validation errors as a clean JSON response.

    Pydantic's default 422 response is preserved, but we extract the
    human-readable `msg` values for cleaner client-facing error messages.
    """
    # Extract the first meaningful error message
    errors: list[dict[str, Any]] = exc.errors()
    messages: list[str] = []
    for err in errors:
        loc = " → ".join(str(l) for l in err.get("loc", []) if l != "body")
        msg = err.get("msg", "Invalid value.")
        # Strip Pydantic's "Value error, " prefix added in v2
        msg = msg.removeprefix("Value error, ")
        messages.append(f"{loc}: {msg}" if loc else msg)

    return JSONResponse(
        status_code=422,  # 422 Unprocessable Content
        content={
            "detail": messages,
            "hint": (
                "Message must be 1–200 characters and contain exactly one "
                "valid http:// or https:// URL."
            ),
        },
    )


# ── Routes ───────────────────────────────────────────────────────────────────


@app.get(
    "/health",
    summary="Health Check",
    description="Returns the operational status of the application.",
    tags=["System"],
)
async def health_check() -> dict[str, str]:
    """Simple health-check endpoint."""
    return {"status": "ok", "version": settings.app_version}


@app.post(
    "/posting",
    response_model=PostingResponse,
    status_code=status.HTTP_200_OK,
    summary="Publish a message to all platforms",
    description=(
        "Accepts a message with exactly one CTA URL (http/https, ≤200 chars) "
        "and publishes it concurrently to Telegram, Bluesky, Mastodon, "
        "LinkedIn, and Reddit.\n\n"
        "**Validation rules:**\n"
        "- Message must not be empty\n"
        "- Message must not exceed 200 characters\n"
        "- Message must contain exactly one URL\n"
        "- URL must be http or https\n"
        "- URL must be syntactically valid\n\n"
        "**Response:**\n"
        "- `success`: `true` only when all configured platforms publish\n"
        "- `results`: per-platform outcome with status, URL, timestamp\n"
    ),
    response_description=(
        "Publishing results for each platform. `success` is true only when "
        "all configured platforms succeed."
    ),
    tags=["Posting"],
)
async def post_message(payload: MessageRequest) -> PostingResponse:
    """
    Publish *payload.message* to all configured social platforms.

    The service runs all platform integrations concurrently.
    A failure on one platform does not prevent the others from publishing.
    """
    if _posting_service is None:
        # Should not happen in normal operation
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": "PostingService is not initialised."},
        )

    logger.info(
        "POST /posting | message length=%d", len(payload.message)
    )
    response = await _posting_service.post_to_all(payload.message)
    return response


# ── Dev server entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.app_port,
        reload=True,
        log_level="info",
    )
