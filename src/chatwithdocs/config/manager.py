"""
Configuration manager for Edan-V2 to handle AI model settings.
Saves and loads configuration from .env file.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from chatwithdocs.config import settings


class ConfigManager:
    """Manages AI model configuration with persistence."""

    def __init__(self, env_file: Path | None = None):
        self.env_file = env_file or Path(".env")

    def get_current_config(self) -> dict:
        """Get current active configuration."""
        provider = settings.llm_provider.lower()

        config = {
            "provider": provider,
            "llm_available": False,
            "model": None,
            "error": None,
        }

        if provider == "kimi":
            config["model"] = settings.kimi_model
            config["llm_available"] = bool(settings.kimi_api_key)
            if not config["llm_available"]:
                config["error"] = "KIMI_API_KEY not set"

        elif provider == "openai":
            config["model"] = settings.openai_model
            config["llm_available"] = bool(settings.openai_api_key)
            if not config["llm_available"]:
                config["error"] = "OPENAI_API_KEY not set"

        elif provider == "deepseek":
            config["model"] = "deepseek-chat"
            config["llm_available"] = bool(settings.openai_api_key) and "deepseek" in (
                settings.openai_base_url or ""
            )
            if not config["llm_available"]:
                config["error"] = "DEEPSEEK_API_KEY not set"

        elif provider == "ollama":
            config["model"] = settings.ollama_model
            # Check if Ollama is running
            try:
                import requests

                response = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=2)
                config["llm_available"] = response.status_code == 200
                if not config["llm_available"]:
                    config["error"] = "Ollama not running"
            except Exception as e:
                config["llm_available"] = False
                config["error"] = f"Ollama connection failed: {e}"
        else:
            config["error"] = f"Unknown provider: {provider}"

        return config

    def save_config(
        self,
        provider: str,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> bool:
        """Save configuration to .env file.

        Args:
            provider: LLM provider (kimi, openai, deepseek, ollama)
            api_key: API key (for cloud providers)
            model: Model name
            base_url: Custom base URL (optional)

        Returns:
            True if saved successfully
        """
        try:
            lines = []

            # Read existing .env if it exists
            if self.env_file.exists():
                with open(self.env_file, "r") as f:
                    lines = f.readlines()

            # Build new config dict
            new_vars = {"LLM_PROVIDER": provider}

            if provider == "kimi":
                if api_key:
                    new_vars["KIMI_API_KEY"] = api_key
                if model:
                    new_vars["KIMI_MODEL"] = model

            elif provider == "openai":
                if api_key:
                    new_vars["OPENAI_API_KEY"] = api_key
                if model:
                    new_vars["OPENAI_MODEL"] = model

            elif provider == "deepseek":
                if api_key:
                    new_vars["OPENAI_API_KEY"] = api_key
                new_vars["OPENAI_BASE_URL"] = base_url or "https://api.deepseek.com/v1"
                new_vars["OPENAI_MODEL"] = model or "deepseek-chat"

            elif provider == "ollama":
                if model:
                    new_vars["OLLAMA_MODEL"] = model

            # Update existing lines or add new ones
            updated_vars = set()
            new_lines = []

            for line in lines:
                line = line.strip()
                if not line or line.startswith("#"):
                    new_lines.append(line)
                    continue

                if "=" in line:
                    key = line.split("=")[0]
                    if key in new_vars:
                        new_lines.append(f"{key}={new_vars[key]}")
                        updated_vars.add(key)
                    else:
                        new_lines.append(line)

            # Add any new variables that weren't updated
            for key, value in new_vars.items():
                if key not in updated_vars:
                    new_lines.append(f"{key}={value}")

            # Write back to file
            with open(self.env_file, "w") as f:
                f.write("\n".join(new_lines) + "\n")

            # Also update current environment
            for key, value in new_vars.items():
                os.environ[key] = value

            return True

        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def load_available_ollama_models(self) -> list[str]:
        """Get list of available Ollama models."""
        try:
            import requests

            response = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=2)
            if response.status_code == 200:
                data = response.json()
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            pass
        return []

    def test_connection(
        self, provider: str, api_key: str | None = None, model: str | None = None
    ) -> tuple[bool, str]:
        """Test connection to a provider.

        Args:
            provider: Provider name
            api_key: Optional API key to test (if not provided, uses settings)
            model: Optional model name to test with

        Returns:
            (success, message)
        """
        if provider == "kimi":
            test_key = api_key or settings.kimi_api_key
            test_model = model or settings.kimi_model
            if not test_key:
                return False, "API key not configured"
            try:
                from openai import OpenAI

                client = OpenAI(api_key=test_key, base_url=settings.kimi_base_url)
                # Try a simple request
                response = client.chat.completions.create(
                    model=test_model,
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=5,
                )
                return True, f"Connected to {test_model}"
            except Exception as e:
                return False, str(e)

        elif provider == "openai":
            test_key = api_key or settings.openai_api_key
            test_model = model or settings.openai_model
            if not test_key:
                return False, "API key not configured"
            try:
                from openai import OpenAI

                client = OpenAI(api_key=test_key)
                response = client.chat.completions.create(
                    model=test_model,
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=5,
                )
                return True, f"Connected to {test_model}"
            except Exception as e:
                return False, str(e)

        elif provider == "deepseek":
            test_key = api_key or settings.openai_api_key
            if not test_key:
                return False, "API key not configured"
            try:
                from openai import OpenAI

                client = OpenAI(
                    api_key=test_key,
                    base_url="https://api.deepseek.com/v1",
                )
                response = client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=5,
                )
                return True, "Connected to DeepSeek"
            except Exception as e:
                return False, str(e)

        elif provider == "ollama":
            test_model = model or settings.ollama_model
            try:
                import requests

                response = requests.get(f"{settings.ollama_base_url}/api/tags", timeout=3)
                if response.status_code == 200:
                    data = response.json()
                    models = [m["name"] for m in data.get("models", [])]
                    if test_model in models or f"{test_model}:latest" in models:
                        return True, f"Ollama running with {test_model}"
                    elif models:
                        return True, f"Ollama running. Available: {', '.join(models[:3])}"
                    else:
                        return True, "Ollama running but no models installed"
                else:
                    return False, f"Ollama returned status {response.status_code}"
            except Exception as e:
                return False, f"Cannot connect to Ollama: {e}"

        return False, f"Unknown provider: {provider}"
