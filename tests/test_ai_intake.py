"""Tests for AI intake service — provider factory, parsing, context building."""

import pytest

from app.services.ai_intake import (
    DisabledProvider,
    HTTPProvider,
    ParsedRequest,
    get_provider,
)


class TestDisabledProvider:
    """Disabled provider should return empty results gracefully."""

    @pytest.mark.asyncio
    async def test_transcribe_returns_empty(self):
        provider = DisabledProvider()
        result = await provider.transcribe_audio(b"fake audio", "audio/ogg")
        assert result == ""

    @pytest.mark.asyncio
    async def test_parse_returns_zero_confidence(self):
        provider = DisabledProvider()
        result = await provider.parse_request("установить розетку", "catalog context")
        assert isinstance(result, ParsedRequest)
        assert result.confidence == 0
        assert result.raw_text == "установить розетку"

    @pytest.mark.asyncio
    async def test_explain_returns_empty(self):
        provider = DisabledProvider()
        result = await provider.explain_estimate({"items": []})
        assert result == ""


class TestParsedRequest:
    """ParsedRequest dataclass tests."""

    def test_defaults(self):
        pr = ParsedRequest(raw_text="test")
        assert pr.raw_text == "test"
        assert pr.confidence == 0.0
        assert pr.detected_items == []
        assert pr.unresolved_questions == []
        assert pr.risk_flags == []
        assert pr.detected_profession is None
        assert pr.summary is None

    def test_with_data(self):
        pr = ParsedRequest(
            raw_text="нужно поменять смеситель",
            detected_profession="сантехника",
            detected_items=[{"code": "PL-FAUCET", "name": "Замена смесителя", "qty": 1}],
            confidence=0.85,
            summary="Замена смесителя на кухне",
        )
        assert pr.detected_profession == "сантехника"
        assert len(pr.detected_items) == 1
        assert pr.confidence == 0.85


class TestProviderFactory:
    """Test get_provider returns correct provider based on config."""

    def test_disabled_by_default(self, monkeypatch):
        """When AI module is disabled, should return DisabledProvider."""
        monkeypatch.setattr("app.services.ai_intake.is_enabled", lambda *a, **kw: False)
        provider = get_provider()
        assert isinstance(provider, DisabledProvider)

    def test_http_provider_when_enabled(self, monkeypatch):
        """When AI is enabled with config, should return HTTPProvider."""
        monkeypatch.setattr("app.services.ai_intake.is_enabled", lambda *a, **kw: True)

        class FakeSettings:
            ai_provider = "openai"
            ai_api_url = "https://api.example.com/v1"
            ai_api_key = "sk-test-key"
            ai_model = "gpt-4"
            ai_timeout_sec = 30

        monkeypatch.setattr("app.services.ai_intake.get_settings", lambda: FakeSettings())
        provider = get_provider()
        assert isinstance(provider, HTTPProvider)
        assert provider.api_url == "https://api.example.com/v1"
        assert provider.model == "gpt-4"

    def test_disabled_when_no_key(self, monkeypatch):
        """Even if module enabled, no API key means disabled."""
        monkeypatch.setattr("app.services.ai_intake.is_enabled", lambda *a, **kw: True)

        class FakeSettings:
            ai_provider = "openai"
            ai_api_url = "https://api.example.com/v1"
            ai_api_key = ""
            ai_model = "gpt-4"
            ai_timeout_sec = 30

        monkeypatch.setattr("app.services.ai_intake.get_settings", lambda: FakeSettings())
        provider = get_provider()
        assert isinstance(provider, DisabledProvider)
