"""OpenAI Chat Completions-compatible provider using the Python standard library."""

from __future__ import annotations

import asyncio
import json
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


class UrllibTransport:
    async def post(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        return await asyncio.to_thread(
            self._post_sync, url, headers, payload, timeout
        )

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
            raise ProviderError(
                f"Provider returned HTTP {exc.code}"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise ProviderError("Provider request failed") from exc
        try:
            parsed = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError("Provider returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise ProviderError("Provider response must be a JSON object")
        return status, parsed


class OpenAICompatibleProvider:
    """Adapter for providers implementing the OpenAI Chat Completions format."""

    def __init__(
        self,
        settings: Settings,
        transport: AsyncTransport | None = None,
    ) -> None:
        if not settings.api_key:
            raise ConfigurationError(
                "CITRUSCARE_API_KEY is required for this provider"
            )
        self.settings = settings
        self.transport = transport or UrllibTransport()

    async def complete(
        self,
        messages: Sequence[Message],
        tools: Sequence[Mapping[str, Any]],
    ) -> AssistantTurn:
        payload: dict[str, Any] = {
            "model": self.settings.model,
            "messages": [self._serialize_message(message) for message in messages],
        }
        if tools:
            payload["tools"] = list(tools)
            payload["tool_choice"] = "auto"
        status, response = await self.transport.post(
            f"{self.settings.base_url.rstrip('/')}/chat/completions",
            {
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
            payload,
            self.settings.request_timeout,
        )
        if status < 200 or status >= 300:
            raise ProviderError(f"Provider returned HTTP {status}")
        return self._parse_response(response)

    @staticmethod
    def _serialize_message(message: Message) -> dict[str, Any]:
        serialized: dict[str, Any] = {
            "role": message.role,
            "content": message.content,
        }
        if message.tool_call_id:
            serialized["tool_call_id"] = message.tool_call_id
        if message.name:
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
