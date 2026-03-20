"""AI intake service: transcription, request parsing, estimate generation.

Provider-agnostic. Supports switching between providers via config.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.config import get_settings
from app.core.module_registry import is_enabled

logger = logging.getLogger(__name__)


@dataclass
class ParsedRequest:
    """Result of AI parsing a client's text/voice message."""
    raw_text: str
    detected_profession: str | None = None
    detected_items: list[dict] | None = None  # [{"code": "...", "name": "...", "qty": 1}]
    confidence: float = 0.0
    unresolved_questions: list[str] | None = None
    risk_flags: list[str] | None = None
    summary: str | None = None


class AIProvider(ABC):
    """Abstract AI provider interface."""

    @abstractmethod
    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str) -> str:
        """Convert audio to text."""

    @abstractmethod
    async def parse_request(self, text: str, catalog_context: str) -> ParsedRequest:
        """Parse a client request into structured data."""

    @abstractmethod
    async def explain_estimate(self, estimate_data: dict) -> str:
        """Generate human-readable estimate explanation."""


class DisabledProvider(AIProvider):
    """Stub when AI is disabled."""

    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str) -> str:
        return ""

    async def parse_request(self, text: str, catalog_context: str) -> ParsedRequest:
        return ParsedRequest(raw_text=text, confidence=0)

    async def explain_estimate(self, estimate_data: dict) -> str:
        return ""


class HTTPProvider(AIProvider):
    """Generic HTTP-based AI provider (OpenAI-compatible API)."""

    def __init__(self, api_url: str, api_key: str, model: str, timeout: int = 30):
        self.api_url = api_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str) -> str:
        import httpx
        # Implementation depends on specific provider's transcription API
        # For now, return empty — to be implemented per provider
        logger.info("Audio transcription not yet implemented for this provider")
        return ""

    async def parse_request(self, text: str, catalog_context: str) -> ParsedRequest:
        import httpx
        import json

        system_prompt = self._build_system_prompt(catalog_context)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": text},
                        ],
                        "temperature": 0.1,
                    },
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]

                # Try to parse as JSON
                try:
                    parsed = json.loads(content)
                    return ParsedRequest(
                        raw_text=text,
                        detected_profession=parsed.get("profession"),
                        detected_items=parsed.get("items", []),
                        confidence=parsed.get("confidence", 0.5),
                        unresolved_questions=parsed.get("questions", []),
                        risk_flags=parsed.get("risks", []),
                        summary=parsed.get("summary", ""),
                    )
                except json.JSONDecodeError:
                    return ParsedRequest(raw_text=text, summary=content, confidence=0.3)

        except Exception as e:
            logger.error("AI parse_request failed: %s", e)
            return ParsedRequest(raw_text=text, confidence=0)

    async def explain_estimate(self, estimate_data: dict) -> str:
        return ""  # TODO: implement with provider

    def _build_system_prompt(self, catalog_context: str) -> str:
        return f"""Ты — ассистент платформы МастерБот. Твоя задача — по описанию клиента определить нужные работы из каталога.

КАТАЛОГ РАБОТ:
{catalog_context}

ПРАВИЛА:
1. Определи профессию: электрика, сантехника, сборка мебели
2. Подбери подходящие работы из каталога (по коду)
3. Укажи количество если понятно
4. Задай уточняющие вопросы если информации недостаточно
5. Отметь риски (сложный доступ, нестандартные условия)

ФОРМАТ ОТВЕТА (JSON):
{{
  "profession": "электрика|сантехника|сборка мебели",
  "items": [{{"code": "EL-PT-SOCKET-INNER", "name": "...", "qty": 1}}],
  "confidence": 0.8,
  "questions": ["Какой материал стен?"],
  "risks": [],
  "summary": "Краткое описание для клиента"
}}"""


def get_provider() -> AIProvider:
    """Factory: return the configured AI provider."""
    if not is_enabled("module.ai_intake", default=False):
        return DisabledProvider()

    settings = get_settings()
    if settings.ai_provider == "disabled":
        return DisabledProvider()

    return HTTPProvider(
        api_url=settings.ai_api_url,
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        timeout=settings.ai_timeout_sec,
    )
