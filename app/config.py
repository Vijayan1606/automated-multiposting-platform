"""
Application configuration.

Loads all credentials and settings from environment variables using
pydantic-settings. Each platform exposes an `is_configured` property
that returns True only when every required variable for that platform
is non-empty, allowing the system to report unconfigured platforms
gracefully without crashing.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Central configuration loaded from environment variables.

    Variables are read from a `.env` file in the working directory
    (if present) and can be overridden by real environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ────────────────────────────────────────────────────────
    app_title: str = "Automated Multi-Platform Posting System"
    app_version: str = "1.0.0"
    app_port: int = 4000

    # ── Telegram ───────────────────────────────────────────────────────────
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # ── Bluesky (AT Protocol) ──────────────────────────────────────────────
    bluesky_identifier: str = ""
    bluesky_app_password: str = ""

    # ── Mastodon ───────────────────────────────────────────────────────────
    mastodon_instance_url: str = ""
    mastodon_access_token: str = ""

    # ── LinkedIn ───────────────────────────────────────────────────────────
    linkedin_access_token: str = ""
    linkedin_person_urn: str = ""

    # ── Reddit ─────────────────────────────────────────────────────────────
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    reddit_username: str = ""
    reddit_password: str = ""
    reddit_user_agent: str = "python:automated-posting:v1.0.0"
    reddit_subreddit: str = ""

    # ── Computed: platform readiness ───────────────────────────────────────

    @property
    def telegram_configured(self) -> bool:
        """True when both Telegram credentials are present."""
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def bluesky_configured(self) -> bool:
        """True when both Bluesky credentials are present."""
        return bool(self.bluesky_identifier and self.bluesky_app_password)

    @property
    def mastodon_configured(self) -> bool:
        """True when both Mastodon credentials are present."""
        return bool(self.mastodon_instance_url and self.mastodon_access_token)

    @property
    def linkedin_configured(self) -> bool:
        """True when both LinkedIn credentials are present."""
        return bool(self.linkedin_access_token and self.linkedin_person_urn)

    @property
    def reddit_configured(self) -> bool:
        """True when all required Reddit credentials are present."""
        return bool(
            self.reddit_client_id
            and self.reddit_client_secret
            and self.reddit_username
            and self.reddit_password
            and self.reddit_subreddit
        )


# Singleton instance used application-wide
settings = Settings()
