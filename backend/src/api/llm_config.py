"""BYOK LLM credential management API.

Lets a user supply their own OpenAI / Azure OpenAI / Claude credentials from
the frontend, validate them with a lightweight connectivity check, and store
them (encrypted, in-memory only, TTL'd) for use by later generation jobs.

Security notes:
- Raw API keys are accepted over HTTPS in the request body only for the
  duration of the request; they are encrypted immediately via
  `src.security.crypto` and only the resulting `credentialId` is ever
  returned to the client.
- Credentials are never logged. Do not add print/log statements that include
  request bodies or decrypted credential fields in this module.
- Credentials are never persisted to disk or any external store.
"""

from __future__ import annotations

from typing import Literal, Optional

import requests
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from src.orchestrator.credential_store import CredentialStore
from src.security.shared_auth import AuthUser, require_rate_limit, require_user

router = APIRouter()

credential_store: Optional[CredentialStore] = None


def init_llm_config_routes(store: CredentialStore) -> None:
    global credential_store
    credential_store = store


Provider = Literal["openai", "azure_openai", "claude"]


class LLMCredentialInput(BaseModel):
    provider: Provider
    api_key: str = Field(min_length=1)
    model: str = Field(min_length=1)
    azure_domain: Optional[str] = None
    azure_api_version: Optional[str] = None
    cookie: Optional[str] = None
    label: str = ""


class TestConnectionResponse(BaseModel):
    success: bool
    message: str


class ConfigureResponse(BaseModel):
    credentialId: str
    provider: Provider


def _validate_provider_fields(payload: LLMCredentialInput) -> None:
    if payload.provider == "azure_openai":
        if not payload.azure_domain or not payload.azure_api_version:
            raise HTTPException(
                status_code=400,
                detail="azure_domain and azure_api_version are required for Azure OpenAI.",
            )


def _test_openai(api_key: str) -> None:
    response = requests.get(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"OpenAI rejected the credentials (HTTP {response.status_code}).")


def _test_azure_openai(api_key: str, domain: str, api_version: str, cookie: Optional[str]) -> None:
    headers = {"api-key": api_key}
    if cookie:
        headers["Cookie"] = cookie
    response = requests.get(
        f"https://{domain}.openai.azure.com/openai/deployments",
        headers=headers,
        params={"api-version": api_version},
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Azure OpenAI rejected the credentials (HTTP {response.status_code}).")


def _test_claude(api_key: str) -> None:
    response = requests.get(
        "https://api.anthropic.com/v1/models",
        headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Claude (Anthropic) rejected the credentials (HTTP {response.status_code}).")


@router.post("/llm/test-connection", response_model=TestConnectionResponse)
async def test_connection(
    request: Request,
    payload: LLMCredentialInput,
    user: AuthUser = Depends(require_user),
) -> TestConnectionResponse:
    _ = user
    await require_rate_limit(request, "llm_test")
    _validate_provider_fields(payload)
    try:
        if payload.provider == "openai":
            _test_openai(payload.api_key)
        elif payload.provider == "azure_openai":
            _test_azure_openai(
                payload.api_key,
                payload.azure_domain or "",
                payload.azure_api_version or "",
                payload.cookie,
            )
        elif payload.provider == "claude":
            _test_claude(payload.api_key)
        else:
            raise HTTPException(status_code=400, detail="Unsupported provider")
    except RuntimeError as exc:
        return TestConnectionResponse(success=False, message=str(exc))
    except requests.RequestException as exc:
        return TestConnectionResponse(success=False, message=f"Connection failed: {exc}")

    return TestConnectionResponse(success=True, message="Connection successful.")


@router.post("/llm/configure", response_model=ConfigureResponse)
async def configure(
    request: Request,
    payload: LLMCredentialInput,
    user: AuthUser = Depends(require_user),
) -> ConfigureResponse:
    _ = user
    await require_rate_limit(request, "llm_configure")
    if credential_store is None:
        raise HTTPException(status_code=500, detail="Credential store not initialized")

    _validate_provider_fields(payload)

    fields = {
        "api_key": payload.api_key,
        "model": payload.model,
        "azure_domain": payload.azure_domain,
        "azure_api_version": payload.azure_api_version,
        "cookie": payload.cookie,
    }
    credential_id = await credential_store.save(payload.provider, fields, label=payload.label)
    return ConfigureResponse(credentialId=credential_id, provider=payload.provider)


@router.delete("/llm/{credential_id}")
async def delete_credential(
    request: Request,
    credential_id: str,
    user: AuthUser = Depends(require_user),
) -> dict[str, bool]:
    _ = user
    await require_rate_limit(request, "llm_delete")
    if credential_store is None:
        raise HTTPException(status_code=500, detail="Credential store not initialized")
    deleted = await credential_store.delete(credential_id)
    return {"deleted": deleted}
