from __future__ import annotations

import unittest
from collections.abc import Mapping
from typing import Any

from citruscare import (
    ConfigurationError,
    Message,
    OpenAICompatibleProvider,
    ProviderError,
    Settings,
)


class FakeTransport:
    def __init__(self, status: int, response: Mapping[str, Any]) -> None:
        self.status = status
        self.response = response
        self.request: tuple[str, Mapping[str, str], Mapping[str, Any], float] | None = (
            None
        )

    async def post(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, Any],
        timeout: float,
    ) -> tuple[int, Mapping[str, Any]]:
        self.request = (url, headers, payload, timeout)
        return self.status, self.response


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_parses_text_response_and_constructs_request(self) -> None:
        transport = FakeTransport(
            200, {"choices": [{"message": {"content": "Hello", "tool_calls": []}}]}
        )
        provider = OpenAICompatibleProvider(
            Settings(api_key="secret", model="test-model"), transport
        )
        result = await provider.complete([Message("user", "Hi", name="client")], [])
        self.assertEqual(result.content, "Hello")
        self.assertEqual(
            transport.request[0], "https://api.openai.com/v1/chat/completions"
        )
        self.assertEqual(transport.request[1]["Authorization"], "Bearer secret")
        self.assertEqual(transport.request[2]["messages"][0]["name"], "client")
        self.assertNotIn("tools", transport.request[2])

    async def test_parses_tool_calls(self) -> None:
        provider = OpenAICompatibleProvider(
            Settings(api_key="secret"),
            FakeTransport(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "function": {
                                            "name": "lookup",
                                            "arguments": '{"term":"test"}',
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                },
            ),
        )
        result = await provider.complete([Message("user", "Find")], [])
        self.assertEqual(result.tool_calls[0].arguments, {"term": "test"})

    async def test_rejects_http_error_and_malformed_response(self) -> None:
        provider = OpenAICompatibleProvider(
            Settings(api_key="secret"),
            FakeTransport(429, {}),
        )
        with self.assertRaisesRegex(ProviderError, "429"):
            await provider.complete([Message("user", "Hi")], [])
        malformed = OpenAICompatibleProvider(
            Settings(api_key="secret"), FakeTransport(200, {})
        )
        with self.assertRaises(ProviderError):
            await malformed.complete([Message("user", "Hi")], [])

    def test_requires_api_key(self) -> None:
        with self.assertRaises(ConfigurationError):
            OpenAICompatibleProvider(Settings())


if __name__ == "__main__":
    unittest.main()
