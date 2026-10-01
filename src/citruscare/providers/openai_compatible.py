"""OpenAI Chat Completions-compatible provider using the Python standard library."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from citruscare.core.config import Settings
from citruscare.core.errors import ConfigurationError, ProviderError
from citruscare.core.messages import AssistantTurn, Message, ToolCall


class AsyncTransport(Protocol):
    async def post(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]: ...

    async def get_json(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]: ...


class UrllibTransport:
    async def post(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        return await asyncio.to_thread(self._post_sync, url, headers, payload, timeout)

    async def get_json(
        self,
        url: str,
        headers: Mapping[str, str],
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        return await asyncio.to_thread(self._get_sync, url, headers, timeout)

    @staticmethod
    def _get_sync(
        url: str,
        headers: Mapping[str, str],
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        request = Request(url, headers=dict(headers), method="GET")
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read()
                status = response.status
        except HTTPError as exc:
            raise _http_provider_error(exc.code) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderError(
                "Provider request failed",
                code="LLM_PROVIDER_UNAVAILABLE",
                retryable=True,
            ) from exc
        return _parse_json_object(body, status)

    @staticmethod
    def _post_sync(
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=dict(headers),
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read()
                status = response.status
        except HTTPError as exc:
            raise _http_provider_error(exc.code) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderError(
                "Provider request failed",
                code="LLM_PROVIDER_UNAVAILABLE",
                retryable=True,
            ) from exc
        return _parse_json_object(body, status)


def _http_provider_error(status: int) -> ProviderError:
    code_by_status = {
        400: "LLM_PROVIDER_INVALID_REQUEST",
        401: "LLM_PROVIDER_AUTH_FAILED",
        403: "LLM_PROVIDER_PERMISSION_DENIED",
        404: "LLM_MODEL_NOT_FOUND",
        408: "LLM_PROVIDER_TIMEOUT",
        429: "LLM_PROVIDER_RATE_LIMITED",
    }
    return ProviderError(
        f"Provider returned HTTP {status}",
        code=code_by_status.get(status, "LLM_PROVIDER_UNAVAILABLE"),
        retryable=status in {408, 429, 500, 502, 503, 504},
        status_code=status,
    )


def _parse_json_object(body: bytes, status: int) -> tuple[int, Mapping[str, Any]]:
    try:
        parsed = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderError(
            "Provider returned invalid JSON",
            code="LLM_PROVIDER_INVALID_RESPONSE",
        ) from exc
    if not isinstance(parsed, dict):
        raise ProviderError(
            "Provider response must be a JSON object",
            code="LLM_PROVIDER_INVALID_RESPONSE",
        )
    return status, parsed


class OpenAICompatibleProvider:
    """Adapter for providers implementing the OpenAI Chat Completions format."""

    def __init__(
        self,
        settings: Settings,
        transport: AsyncTransport | None = None,
        *,
        include_message_names: bool = True,
    ) -> None:
        if not settings.api_key:
            raise ConfigurationError("Provider API credentials are required")
        self.settings = settings
        self.transport = transport or UrllibTransport()
        self.include_message_names = include_message_names

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[Mapping[str, Any]],
    ) -> AssistantTurn:
        turn, _ = await self.complete_with_metadata(messages, tools)
        return turn

    async def complete_with_metadata(
        self,
        messages: Sequence[Message],
        tools: Sequence[Mapping[str, Any]],
        *,
        request_id: str | None = None,
        structured: bool = False,
    ) -> tuple[AssistantTurn, Mapping[str, Any]]:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [
                self._serialize_message(
                    message, include_name=self.include_message_names
                )
                for message in messages
            ],
        }
        if tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = "auto"
        if structured:
            payload["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        if request_id:
            headers["X-Request-ID"] = request_id
        started = time.perf_counter()
        status, response = await self.transport.post(
            f"{self.settings.base_url.rstrip('/')}/chat/completions",
            headers,
            payload,
            self.settings.request_timeout,
        )
        if status < 200 or status >= 300:
            raise _http_provider_error(status)
        turn = self._parse_response(response)
        raw_usage = response.get("usage", {})
        usage = raw_usage if isinstance(raw_usage, Mapping) else {}
        metadata = {
            "latency_ms": round((time.perf_counter() - started) * 1000, 3),
            "request_id": request_id,
            "usage": {
                key: usage[key]
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                if isinstance(usage.get(key), int) and usage[key] >= 0
            },
            "provider_request_id": response.get("id")
            if isinstance(response.get("id"), str)
            else None,
        }
        return turn, metadata

    @staticmethod
    def _serialize_message(
        message: Message, *, include_name: bool = True
    ) -> dict[str, Any]:
        serialized: dict[str, Any] = {
            "role": message.role,
            "content": message.content,
        }
        if message.tool_call_id:
            serialized["tool_call_id"] = message.tool_call_id
        if include_name and message.name:
            serialized["name"] = message.name
        if message.tool_calls:
            serialized["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments),
                    },
                }
                for call in message.tool_calls
            ]
        return serialized

    @staticmethod
    def _parse_response(response: Mapping[str, Any]) -> AssistantTurn:
        try:
            choices = response["choices"]
            message = choices[0]["message"]
            content = message.get("content")
            raw_tool_calls = message.get("tool_calls", [])
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Provider response is missing a chat message") from exc
        if content is not None and not isinstance(content, str):
            raise ProviderError("Provider message content must be a string or null")
        if not isinstance(raw_tool_calls, list):
            raise ProviderError("Provider tool_calls must be a list")
        calls: list[ToolCall] = []
        for raw_call in raw_tool_calls:
            try:
                call_id = raw_call["id"]
                function = raw_call["function"]
                name = function["name"]
                arguments = json.loads(function["arguments"])
            except (KeyError, TypeError, json.JSONDecodeError) as exc:
                raise ProviderError("Provider returned an invalid tool call") from exc
            if (
                not isinstance(call_id, str)
                or not isinstance(name, str)
                or not isinstance(arguments, dict)
            ):
                raise ProviderError("Provider returned an invalid tool call")
            calls.append(ToolCall(call_id, name, arguments))
        return AssistantTurn(content=content, tool_calls=tuple(calls))
