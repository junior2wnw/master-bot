"""AI intake service: transcription, request parsing, estimate generation.

Provider-agnostic. Supports switching between providers via config.
Uses OpenAI-compatible API for both chat and transcription.
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.config import get_settings
from app.core.module_registry import is_enabled

logger = logging.getLogger(__name__)


@dataclass
class ParsedRequest:
    """Result of AI parsing a client's text/voice message."""
    raw_text: str
    detected_profession: str | None = None
    detected_items: list[dict] = field(default_factory=list)  # [{"code": "...", "name": "...", "qty": 1}]
    confidence: float = 0.0
    unresolved_questions: list[str] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
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
    """Generic HTTP-based AI provider (OpenAI-compatible API).

    Works with: OpenAI, YandexGPT (via proxy), GigaChat, local LLMs, etc.
    """

    def __init__(self, api_url: str, api_key: str, model: str, timeout: int = 30):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def transcribe_audio(self, audio_bytes: bytes, mime_type: str) -> str:
        """Transcribe audio using OpenAI-compatible Whisper API."""
        import httpx

        ext = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/wav": "wav"}.get(mime_type, "ogg")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/audio/transcriptions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    data={"model": "whisper-1", "language": "ru"},
                    files={"file": (f"audio.{ext}", audio_bytes, mime_type)},
                )
                response.raise_for_status()
                data = response.json()
                return data.get("text", "")
        except Exception as e:
            logger.error("Audio transcription failed: %s", e)
            return ""

    async def parse_request(self, text: str, catalog_context: str) -> ParsedRequest:
        """Parse client text using chat completions API."""
        import httpx

        system_prompt = _build_system_prompt(catalog_context)
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": text},
                        ],
                        "temperature": 0.1,
                        "max_tokens": 2000,
                    },
                )
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]

                # Try to extract JSON from response (may be wrapped in markdown)
                json_str = content
                if "```json" in content:
                    json_str = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    json_str = content.split("```")[1].split("```")[0]

                try:
                    parsed = json.loads(json_str.strip())
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
                    # AI returned plain text instead of JSON
                    return ParsedRequest(
                        raw_text=text, summary=content, confidence=0.3,
                    )

        except Exception as e:
            logger.error("AI parse_request failed: %s", e)
            return ParsedRequest(raw_text=text, confidence=0)

    async def explain_estimate(self, estimate_data: dict) -> str:
        """Generate human-readable explanation of an estimate."""
        import httpx

        prompt = (
            "Объясни клиенту эту смету простым языком. "
            "Кратко опиши каждую работу и зачем она нужна.\n\n"
            f"Смета: {json.dumps(estimate_data, ensure_ascii=False)}"
        )
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": "Ты — ассистент платформы МастерБот. Объясняй понятно и дружелюбно."},
                            {"role": "user", "content": prompt},
                        ],
                        "temperature": 0.3,
                        "max_tokens": 1000,
                    },
                )
                response.raise_for_status()
                data = response.json()
                return data["choices"][0]["message"]["content"]
        except Exception as e:
            logger.error("AI explain_estimate failed: %s", e)
            return ""


def _build_system_prompt(catalog_context: str) -> str:
    """Build the system prompt for request parsing."""
    return f"""Ты — ИИ-ассистент платформы МастерБот. Помогаешь клиентам определить нужные работы.

КАТАЛОГ РАБОТ (код — название — цена, ₽):
{catalog_context}

ТВОЯ ЗАДАЧА:
По описанию клиента определи:
1. Профессию: электрика, сантехника, сборка мебели
2. Конкретные работы из каталога (используй точные коды)
3. Количество (если понятно из контекста)
4. Уточняющие вопросы (если информации мало)
5. Риски (сложный доступ, нестандартные условия, потенциальные проблемы)

ПРАВИЛА:
- Используй ТОЛЬКО работы из каталога выше
- Если не уверен — задай вопрос, не угадывай
- Всегда добавляй выезд мастера (#CALL_OUT) если это визит на дом
- Учитывай сложность: бетонные стены → коэффициент, высотные работы → коэффициент
- Если клиент описывает что-то необычное — отметь как risk

ФОРМАТ ОТВЕТА (строго JSON):
{{
  "profession": "электрика",
  "items": [
    {{"code": "EL-PT-SOCKET-INNER", "name": "Установка розетки внутренней", "qty": 2}},
    {{"code": "#CALL_OUT", "name": "Выезд мастера", "qty": 1}}
  ],
  "confidence": 0.85,
  "questions": ["Какой материал стен — бетон или гипс?"],
  "risks": [],
  "summary": "Установка 2 розеток. Точная цена зависит от материала стен."
}}"""


def get_provider() -> AIProvider:
    """Factory: return the configured AI provider."""
    if not is_enabled("module.ai_intake", default=False):
        return DisabledProvider()

    settings = get_settings()
    if settings.ai_provider == "disabled" or not settings.ai_api_key:
        return DisabledProvider()

    return HTTPProvider(
        api_url=settings.ai_api_url,
        api_key=settings.ai_api_key,
        model=settings.ai_model,
        timeout=settings.ai_timeout_sec,
    )


async def build_catalog_context(session, profession_id: int | None = None, limit: int = 100) -> str:
    """Build compact catalog context string for AI prompts."""
    from sqlalchemy import select
    from app.models.catalog import ServiceItem, SharedOperation

    q = (
        select(ServiceItem.code, ServiceItem.name, ServiceItem.price_recommended, ServiceItem.unit)
        .where(ServiceItem.is_active == True)
        .order_by(ServiceItem.is_popular.desc(), ServiceItem.sort_order)
        .limit(limit)
    )
    if profession_id:
        q = q.where(ServiceItem.profession_id == profession_id)

    result = await session.execute(q)
    lines = [f"{r.code} — {r.name} — {r.price_recommended}₽/{r.unit}" for r in result.all()]

    # Add shared operations
    ops = await session.execute(select(SharedOperation).where(SharedOperation.is_active == True))
    for op in ops.scalars():
        lines.append(f"{op.code} — {op.name}")

    return "\n".join(lines)


async def process_voice(session, audio_bytes: bytes, mime_type: str = "audio/ogg") -> ParsedRequest:
    """Full pipeline: transcribe → parse → return structured result."""
    provider = get_provider()

    # Step 1: Transcribe
    text = await provider.transcribe_audio(audio_bytes, mime_type)
    if not text:
        return ParsedRequest(raw_text="", summary="Не удалось распознать речь", confidence=0)

    # Step 2: Parse
    catalog_ctx = await build_catalog_context(session)
    result = await provider.parse_request(text, catalog_ctx)
    return result


async def process_text(session, text: str) -> ParsedRequest:
    """Parse text input using AI."""
    provider = get_provider()
    catalog_ctx = await build_catalog_context(session)
    return await provider.parse_request(text, catalog_ctx)
