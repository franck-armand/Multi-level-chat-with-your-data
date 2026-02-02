"""LLM client for response generation.

Supports multiple providers:
- OpenAI API
- DeepSeek API
- Ollama (local)
- Fallback (deterministic)
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

from chatwithdocs.config import settings

logger = logging.getLogger(__name__)


@dataclass
class LLMMessage:
    """Message for LLM conversation."""

    role: str  # "system", "user", "assistant"
    content: str


@dataclass
class LLMResponse:
    """Response from LLM."""

    content: str
    model: str
    usage: dict | None = None
    error: str | None = None


class BaseLLMClient(ABC):
    """Base class for LLM clients."""

    @abstractmethod
    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Generate response from messages."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the LLM client is available."""
        pass


class OpenAILLMClient(BaseLLMClient):
    """OpenAI-compatible LLM client (works with OpenAI, DeepSeek, etc.)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or settings.openai_api_key
        self.base_url = base_url or settings.openai_base_url
        self.model = model or settings.openai_model
        self._client = None

    def _get_client(self):
        """Lazy initialize OpenAI client."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
                logger.info(f"Initialized OpenAI client with model: {self.model}")
            except ImportError:
                logger.error("openai package not installed. Run: pip install openai")
                raise
        return self._client

    def is_available(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Generate response using OpenAI API."""
        if not self.is_available():
            return LLMResponse(
                content="",
                model=self.model,
                error="OpenAI API key not configured",
            )

        try:
            client = self._get_client()

            # Convert messages to OpenAI format
            openai_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

            response = await client.chat.completions.create(
                model=self.model,
                messages=openai_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return LLMResponse(
                content=response.choices[0].message.content,
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
            )

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return LLMResponse(
                content="",
                model=self.model,
                error=str(e),
            )


class OllamaLLMClient(BaseLLMClient):
    """Ollama local LLM client with model management."""

    DEFAULT_MODEL = "llama3.2"
    RECOMMENDED_MODELS = [
        ("llama3.2", "Llama 3.2 (3B) - Fast, good quality"),
        ("llama3.1", "Llama 3.1 (8B) - Better quality"),
        ("mistral", "Mistral 7B - Very capable"),
        ("qwen2.5", "Qwen 2.5 - Multilingual expert"),
        ("gemma2", "Gemma 2 - Google model"),
        ("phi4", "Phi-4 - Microsoft, coding expert"),
        ("deepseek-r1", "DeepSeek R1 - Reasoning focused"),
        ("llama3.2-vision", "Llama 3.2 Vision - Image support"),
    ]

    def __init__(self, model: str | None = None, base_url: str = "http://localhost:11434"):
        self.model = model or settings.ollama_model or self.DEFAULT_MODEL
        self.base_url = base_url or settings.ollama_base_url
        self._available_models: list[str] | None = None

    def is_available(self) -> bool:
        """Check if Ollama is running."""
        try:
            import requests

            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            if response.status_code == 200:
                # Cache available models
                data = response.json()
                self._available_models = [m["name"] for m in data.get("models", [])]
                return True
            return False
        except Exception:
            return False

    def get_available_models(self) -> list[str]:
        """Get list of installed models."""
        if self._available_models is None:
            try:
                import requests

                response = requests.get(f"{self.base_url}/api/tags", timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    self._available_models = [m["name"] for m in data.get("models", [])]
                else:
                    self._available_models = []
            except Exception:
                self._available_models = []
        return self._available_models

    def is_model_installed(self, model_name: str) -> bool:
        """Check if a specific model is installed."""
        available = self.get_available_models()
        return any(model_name in m for m in available)

    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Generate response using Ollama API."""
        if not self.is_available():
            return LLMResponse(
                content="",
                model=self.model,
                error="Ollama not running. Install from ollama.com and run: ollama run llama3.2",
            )

        # Check if model is installed
        if not self.is_model_installed(self.model):
            available = self.get_available_models()
            available_str = ", ".join(available[:5]) if available else "none"
            return LLMResponse(
                content="",
                model=self.model,
                error=f"Model '{self.model}' not installed. Available: {available_str}. Run: ollama pull {self.model}",
            )

        try:
            import aiohttp

            # Convert messages to Ollama format
            ollama_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": ollama_messages,
                        "stream": False,
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens,
                        },
                    },
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return LLMResponse(
                            content=data["message"]["content"],
                            model=self.model,
                        )
                    else:
                        error_text = await response.text()
                        return LLMResponse(
                            content="",
                            model=self.model,
                            error=f"Ollama error: {error_text}",
                        )

        except Exception as e:
            logger.error(f"Ollama error: {e}")
            return LLMResponse(
                content="",
                model=self.model,
                error=str(e),
            )


class FallbackLLMClient(BaseLLMClient):
    """Fallback client that extracts content from context."""

    def is_available(self) -> bool:
        """Always available."""
        return True

    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Generate deterministic response from context."""
        # Find the last user message
        user_message = None
        for msg in reversed(messages):
            if msg.role == "user":
                user_message = msg.content
                break

        if not user_message:
            return LLMResponse(
                content="I don't have enough information to answer that.",
                model="fallback",
            )

        # Extract context from system message if present
        context = ""
        for msg in messages:
            if msg.role == "system" and "Context:" in msg.content:
                # Extract context section
                parts = msg.content.split("Context:")
                if len(parts) > 1:
                    context = parts[1].split("Question:")[0].strip()

        if not context:
            return LLMResponse(
                content=(
                    "I couldn't find relevant information in your documents to answer "
                    f"this question. Please try rephrasing or upload documents related to: {user_message}"
                ),
                model="fallback",
            )

        # Extract relevant sentences
        sentences = context.split(". ")
        query_words = set(user_message.lower().split())
        relevant = []

        for sentence in sentences[:3]:
            sentence_words = set(sentence.lower().split())
            if query_words & sentence_words:
                relevant.append(sentence)

        if not relevant:
            relevant = sentences[:2]

        answer = ". ".join(relevant)
        if not answer.endswith("."):
            answer += "."

        return LLMResponse(
            content=answer,
            model="fallback",
        )


class KimiLLMClient(BaseLLMClient):
    """Kimi (Moonshot AI) LLM client - K2.5 model support."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or settings.kimi_api_key
        self.base_url = base_url or settings.kimi_base_url
        self.model = model or settings.kimi_model
        self._client = None

    def _get_client(self):
        """Lazy initialize OpenAI client for Kimi API."""
        if self._client is None:
            try:
                from openai import AsyncOpenAI

                self._client = AsyncOpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
                logger.info(f"Initialized Kimi client with model: {self.model}")
            except ImportError:
                logger.error("openai package not installed. Run: pip install openai")
                raise
        return self._client

    def is_available(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Generate response using Kimi API."""
        if not self.is_available():
            return LLMResponse(
                content="",
                model=self.model,
                error="Kimi API key not configured. Get one at: https://platform.moonshot.cn/",
            )

        try:
            client = self._get_client()

            # Convert messages to OpenAI format
            kimi_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

            response = await client.chat.completions.create(
                model=self.model,
                messages=kimi_messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            return LLMResponse(
                content=response.choices[0].message.content,
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
            )

        except Exception as e:
            logger.error(f"Kimi API error: {e}")
            return LLMResponse(
                content="",
                model=self.model,
                error=str(e),
            )


class LLMRouter:
    """Router for LLM clients with fallback support."""

    def __init__(self, provider: str | None = None):
        self.provider = provider or settings.llm_provider
        self._clients: dict[str, BaseLLMClient] = {}
        self._init_clients()

    def _init_clients(self):
        """Initialize all LLM clients."""
        # OpenAI client (works with OpenAI, DeepSeek, any OpenAI-compatible API)
        self._clients["openai"] = OpenAILLMClient()

        # DeepSeek uses OpenAI-compatible API
        if settings.openai_base_url and "deepseek" in settings.openai_base_url.lower():
            self._clients["deepseek"] = OpenAILLMClient(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                model=settings.openai_model,
            )

        # Kimi (Moonshot AI) - K2.5 support
        self._clients["kimi"] = KimiLLMClient()

        # Ollama local LLM
        self._clients["ollama"] = OllamaLLMClient()

        # Fallback client
        self._clients["fallback"] = FallbackLLMClient()

    def get_client(self) -> BaseLLMClient:
        """Get the best available LLM client."""
        # Try requested provider first
        if self.provider in self._clients:
            client = self._clients[self.provider]
            if client.is_available():
                logger.info(f"Using LLM provider: {self.provider}")
                return client

        # Try providers in order of preference
        for name in ["kimi", "openai", "deepseek", "ollama"]:
            if name in self._clients:
                client = self._clients[name]
                if client.is_available():
                    logger.info(f"Using LLM provider: {name}")
                    return client

        # Fallback to deterministic client
        logger.warning("No LLM API configured. Using fallback (limited quality).")
        logger.warning("Set KIMI_API_KEY for best results with Kimi K2.5")
        return self._clients["fallback"]

    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ) -> LLMResponse:
        """Generate response using the best available client."""
        client = self.get_client()
        return await client.generate(messages, temperature, max_tokens)


# Convenience function for quick usage
async def generate_response(
    query: str,
    context: str,
    system_prompt: str | None = None,
    chat_history: List[LLMMessage] | None = None,
) -> str:
    """Generate a response with RAG context.

    Args:
        query: User query
        context: Retrieved context from documents
        system_prompt: Optional custom system prompt
        chat_history: Optional chat history for context

    Returns:
        Generated response text
    """
    router = LLMRouter()

    # Build messages
    if system_prompt is None:
        system_prompt = (
            "You are a helpful assistant that answers questions based on the provided context. "
            "Use only the information from the context to answer. If the context doesn't contain "
            "the answer, say so clearly."
        )

    # Add context to system prompt
    full_system = f"{system_prompt}\n\nContext:\n{context}\n\nAnswer the user's question based on the context above."

    messages = [LLMMessage(role="system", content=full_system)]

    # Add chat history if provided
    if chat_history:
        messages.extend(chat_history)

    # Add current query
    messages.append(LLMMessage(role="user", content=query))

    # Generate response
    response = await router.generate(messages)

    if response.error:
        logger.error(f"LLM generation error: {response.error}")
        return f"I encountered an error generating a response: {response.error}"

    return response.content
