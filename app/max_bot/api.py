"""Minimal async client for the MAX Bot HTTP API."""

from __future__ import annotations

from typing import Any

import httpx


class MaxAPIError(RuntimeError):
    """Raised when the MAX API returns an error response."""


class MaxBotAPI:
    """Thin HTTP client for the subset of MAX API methods we use."""

    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://platform-api.max.ru",
        timeout_sec: int = 30,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": token},
            timeout=max(10, timeout_sec + 5),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def get_me(self) -> dict[str, Any]:
        response = await self._client.get("/me")
        return self._unwrap_response(response)

    async def get_updates(
        self,
        *,
        marker: int | None = None,
        timeout: int = 30,
        limit: int = 100,
        types: list[str] | None = None,
    ) -> dict[str, Any]:
        params: list[tuple[str, str | int]] = [
            ("timeout", max(0, min(timeout, 90))),
            ("limit", max(1, min(limit, 1000))),
        ]
        if marker is not None:
            params.append(("marker", marker))
        if types:
            params.extend(("types", update_type) for update_type in types)

        response = await self._client.get("/updates", params=params)
        return self._unwrap_response(response)

    async def get_subscriptions(self) -> dict[str, Any]:
        response = await self._client.get("/subscriptions")
        return self._unwrap_response(response)

    async def create_subscription(
        self,
        *,
        url: str,
        update_types: list[str] | None = None,
        secret: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"url": url}
        if update_types:
            body["update_types"] = update_types
        if secret:
            body["secret"] = secret

        response = await self._client.post("/subscriptions", json=body)
        return self._unwrap_response(response)

    async def send_message(
        self,
        *,
        text: str,
        user_id: int | None = None,
        chat_id: int | None = None,
        attachments: list[dict[str, Any]] | None = None,
        notify: bool = True,
        format: str = "html",
    ) -> dict[str, Any]:
        if user_id is None and chat_id is None:
            raise ValueError("Either user_id or chat_id must be provided")

        params: dict[str, int] = {}
        if user_id is not None:
            params["user_id"] = user_id
        if chat_id is not None:
            params["chat_id"] = chat_id

        body: dict[str, Any] = {
            "text": text,
            "notify": notify,
            "format": format,
        }
        if attachments:
            body["attachments"] = attachments

        response = await self._client.post("/messages", params=params, json=body)
        return self._unwrap_response(response)

    async def answer_callback(
        self,
        *,
        callback_id: str,
        notification: str | None = None,
        message: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if notification:
            body["notification"] = notification
        if message:
            body["message"] = message

        response = await self._client.post(
            "/answers",
            params={"callback_id": callback_id},
            json=body,
        )
        return self._unwrap_response(response)

    @staticmethod
    def _unwrap_response(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            payload = {"message": response.text}

        if response.is_success:
            return payload

        message = payload.get("message") or payload.get("code") or response.text
        raise MaxAPIError(f"MAX API error {response.status_code}: {message}")
