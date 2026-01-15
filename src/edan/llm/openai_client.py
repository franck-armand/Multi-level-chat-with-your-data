from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from edan.llm.config import LLMConfig


@dataclass
class LLMResult:
    text: str
    used_llm: bool
    error: Optional[str] = None


def openai_narrative(cfg: LLMConfig, prompt: str) -> LLMResult:
    """
    Uses OpenAI-compatible APIs.
    - For OpenAI: Responses API
    - For DeepSeek: Chat Completions API (as in DeepSeek docs)
    """
    if not cfg.enabled:
        return LLMResult(text="", used_llm=False, error=cfg.reason)

    try:
        from openai import OpenAI  # type: ignore
    except Exception as e:
        return LLMResult(text="", used_llm=False, error=f"openai package missing: {e}")

    try:
        client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url)

        if cfg.provider == "deepseek":
            # DeepSeek: Chat Completions endpoint compatibility
            resp = client.chat.completions.create(
                model=cfg.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant. Use only the provided evidence."},
                    {"role": "user", "content": prompt},
                ],
                stream=False,
            )
            text = resp.choices[0].message.content or ""
            return LLMResult(text=text.strip(), used_llm=True)

        # OpenAI: Responses API
        resp = client.responses.create(model=cfg.model, input=prompt)
        text = getattr(resp, "output_text", None) or str(resp)
        return LLMResult(text=text.strip(), used_llm=True)

    except Exception as e:
        return LLMResult(text="", used_llm=False, error=str(e))