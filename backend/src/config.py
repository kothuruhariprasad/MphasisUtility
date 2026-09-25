from __future__ import annotations

import os

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    llm_api_key: str | None = Field(default=None, alias="LLM_API_KEY")
    llm_cookie: str | None = Field(default=None, alias="LLM_COOKIE")
    azure_openai_domain: str | None = Field(default=None, alias="AZURE_OPENAI_DOMAIN")
    azure_openai_api_version: str | None = Field(default=None, alias="AZURE_OPENAI_API_VERSION")
    llm_model_name: str | None = Field(default=None, alias="LLM_MODEL_NAME")
    abl_model: str = Field(default="", alias="ABL_MODEL")
    reasoning_model: str | None = Field(default=None, alias="REASONING_MODEL")
    flow_model: str | None = Field(default=None, alias="FLOW_MODEL")
    max_concurrent_llm_calls: int = Field(default=4, alias="MAX_CONCURRENT_LLM_CALLS")
    session_ttl_seconds: int = Field(default=86400, alias="SESSION_TTL_SECONDS")
    credential_ttl_seconds: int = Field(default=86400, alias="CREDENTIAL_TTL_SECONDS")
    credential_encryption_key: str | None = Field(default=None, alias="CREDENTIAL_ENCRYPTION_KEY")
    verify_enabled: bool = Field(default=True, alias="VERIFY_ENABLED")
    llm_timeout_seconds: int = Field(default=180, alias="LLM_TIMEOUT_SECONDS")
    rate_limit_per_minute: int = Field(default=60, alias="RATE_LIMIT_PER_MINUTE")
    app_password_hash: str | None = Field(default=None, alias="APP_PASSWORD_HASH")
    app_admin_password_hash: str | None = Field(default=None, alias="APP_ADMIN_PASSWORD_HASH")
    session_secret: str | None = Field(default=None, alias="SESSION_SECRET")
    auth_session_ttl_seconds: int = Field(default=28800, alias="AUTH_SESSION_TTL_SECONDS")
    auth_cookie_name: str = Field(default="app_session", alias="AUTH_COOKIE_NAME")
    auth_cookie_same_site: str = Field(default="lax", alias="AUTH_COOKIE_SAMESITE")
    auth_cookie_secure: bool | None = Field(default=None, alias="AUTH_COOKIE_SECURE")
    shared_user_email: str = Field(default="team@local", alias="SHARED_USER_EMAIL")
    shared_admin_email: str = Field(default="admin@local", alias="SHARED_ADMIN_EMAIL")
    allowed_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        alias="ALLOWED_ORIGINS",
    )
    max_upload_mb: int = Field(default=50, alias="MAX_UPLOAD_MB")
    max_zip_entries: int = Field(default=10000, alias="MAX_ZIP_ENTRIES")
    max_zip_uncompressed_mb: int = Field(default=200, alias="MAX_ZIP_UNCOMPRESSED_MB")
    manual_estimate_base_minutes: int = Field(default=20, alias="MANUAL_ESTIMATE_BASE_MINUTES")
    manual_estimate_per_node_minutes: int = Field(default=4, alias="MANUAL_ESTIMATE_PER_NODE_MINUTES")
    manual_estimate_per_entity_minutes: int = Field(default=6, alias="MANUAL_ESTIMATE_PER_ENTITY_MINUTES")
    manual_estimate_per_service_minutes: int = Field(default=18, alias="MANUAL_ESTIMATE_PER_SERVICE_MINUTES")
    manual_estimate_per_condition_minutes: int = Field(default=5, alias="MANUAL_ESTIMATE_PER_CONDITION_MINUTES")
    manual_estimate_supervisor_base_minutes: int = Field(
        default=30,
        
        alias="MANUAL_ESTIMATE_SUPERVISOR_BASE_MINUTES",
    )
    manual_estimate_supervisor_per_intent_minutes: int = Field(
        default=6,
        alias="MANUAL_ESTIMATE_SUPERVISOR_PER_INTENT_MINUTES",
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.allowed_origins.split(",") if item.strip()]


if "LLM_MODEL_NAME" not in os.environ and "llm_model_name" in os.environ:
    os.environ["LLM_MODEL_NAME"] = os.environ["llm_model_name"]


settings = Settings()
