from __future__ import annotations

# Environment variables used for LLM configuration:
# - CHATWITHDOCS_LLM_MODE: "local" or "openai" (default: "local")
# - CHATWITHDOCS_LLM_PROVIDER: "openai" or "deepseek" (default: "openai")
# - CHATWITHDOCS_OPENAI_BASE_URL: Custom base URL for OpenAI-compatible APIs
# - CHATWITHDOCS_OPENAI_MODEL: Model name (defaults: "deepseek-chat" for deepseek, "gpt-5" for openai)
# - OPENAI_API_KEY / DEEPSEEK_API_KEY: API keys for respective providers

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMConfig:
    mode: str  # "local" | "openai"
    provider: str  # "openai" | "deepseek"
    model: str
    enabled: bool
    reason: str
    base_url: str | None
    api_key: str | None


def get_llm_config() -> LLMConfig:
    mode = os.getenv("CHATWITHDOCS_LLM_MODE", "local").strip().lower()
    provider = os.getenv("CHATWITHDOCS_LLM_PROVIDER", "openai").strip().lower()

    if mode != "openai":
        return LLMConfig(
            mode="local",
            provider=provider,
            model="",
            enabled=False,
            reason="local mode",
            base_url=None,
            api_key=None,
        )

    # Provider defaults
    base_url = os.getenv("CHATWITHDOCS_OPENAI_BASE_URL")
    if provider == "deepseek" and not base_url:
        base_url = "https://api.deepseek.com"

    # API key selection
    api_key = os.getenv("OPENAI_API_KEY")
    if provider == "deepseek":
        api_key = os.getenv("DEEPSEEK_API_KEY") or api_key

    if not api_key:
        return LLMConfig(
            mode="openai",
            provider=provider,
            model="",
            enabled=False,
            reason="API key missing (DEEPSEEK_API_KEY / OPENAI_API_KEY)",
            base_url=base_url,
            api_key=None,
        )

    # Model defaults
    model = os.getenv("CHATWITHDOCS_OPENAI_MODEL")
    if not model:
        model = "deepseek-chat" if provider == "deepseek" else "gpt-5"

    return LLMConfig(
        mode="openai",
        provider=provider,
        model=model,
        enabled=True,
        reason="enabled",
        base_url=base_url,
        api_key=api_key,
    )
