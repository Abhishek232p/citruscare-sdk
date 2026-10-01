"""Tool registry with argument validation and normalized failures."""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from citruscare.core.errors import ToolExecutionError
from citruscare.core.messages import ToolCall

ToolHandler = Callable[..., Any]
_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_JSON_TYPES = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


@dataclass(frozen=True, slots=True)
class Tool:
    name: str
    description: str
    parameters: Mapping[str, Any]
    handler: ToolHandler
    required_permissions: frozenset[str] = frozenset()
    risk_level: str = "low"

    def __post_init__(self) -> None:
        if not _NAME_PATTERN.fullmatch(self.name):
            raise ValueError("tool names must be 1-64 letters, digits, '_' or '-'")
        if not self.description.strip():
            raise ValueError("tool description must not be empty")
        if not isinstance(self.parameters, Mapping):
            raise ValueError("tool parameters must be a JSON Schema object")
        if self.parameters.get("type") != "object":
            raise ValueError("tool parameters must use a JSON Schema object")
        properties = self.parameters.get("properties", {})
        required = self.parameters.get("required", [])
        if not isinstance(properties, Mapping) or not isinstance(required, list):
            raise ValueError("tool parameters have invalid properties or required")
        if any(
            not isinstance(name, str) or not isinstance(schema, Mapping)
            for name, schema in properties.items()
        ):
            raise ValueError("tool property schemas must be objects with string names")
        if any(
            schema.get("type") is not None and schema.get("type") not in _JSON_TYPES
            for schema in properties.values()
        ):
            raise ValueError("tool properties use an unsupported JSON type")
        if any(not isinstance(key, str) for key in required):
            raise ValueError("required tool argument names must be strings")
        if any(key not in properties for key in required):
            raise ValueError("required tool arguments must be declared in properties")
        if self.risk_level not in {"low", "moderate", "high"}:
            raise ValueError("risk_level must be low, moderate, or high")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        self.history: list[ToolExecutionRecord] = []

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def provider_schemas(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": dict(tool.parameters),
                },
            }
            for tool in self._tools.values()
        ]

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": dict(tool.parameters),
                "required_permissions": sorted(tool.required_permissions),
                "risk_level": tool.risk_level,
            }
            for tool in self._tools.values()
        ]

    async def invoke(
        self,
        call: ToolCall,
        *,
        permissions: frozenset[str] = frozenset(),
    ) -> Any:
        tool = self._tools.get(call.name)
        if tool is None:
            self.history.append(
                ToolExecutionRecord(call.name, False, "unknown_tool", datetime.now(UTC))
            )
            raise ToolExecutionError(f"Unknown tool '{call.name}'")
        missing_permissions = tool.required_permissions - permissions
        if missing_permissions:
            self.history.append(
                ToolExecutionRecord(
                    call.name, False, "permission_denied", datetime.now(UTC)
                )
            )
            raise ToolExecutionError(f"Permission denied for tool '{call.name}'")
        self._validate_arguments(tool, call.arguments)
        try:
            result = tool.handler(**call.arguments)
            if inspect.isawaitable(result):
                result = await result
            json.dumps(result)
            self.history.append(
                ToolExecutionRecord(call.name, True, "success", datetime.now(UTC))
            )
            return result
        except ToolExecutionError:
            raise
        except Exception as exc:
            self.history.append(
                ToolExecutionRecord(
                    call.name, False, type(exc).__name__, datetime.now(UTC)
                )
            )
            raise ToolExecutionError(
                f"Tool '{tool.name}' failed ({type(exc).__name__})"
            ) from exc

    @staticmethod
    def _validate_arguments(tool: Tool, arguments: Mapping[str, Any]) -> None:
        if not isinstance(arguments, Mapping):
            raise ToolExecutionError(f"Tool '{tool.name}' arguments must be an object")
        properties = tool.parameters.get("properties", {})
        required = tool.parameters.get("required", [])
        missing = [key for key in required if key not in arguments]
        if missing:
            raise ToolExecutionError(
                f"Tool '{tool.name}' is missing required arguments: "
                f"{', '.join(missing)}"
            )
        if tool.parameters.get("additionalProperties") is False:
            unknown = [key for key in arguments if key not in properties]
            if unknown:
                raise ToolExecutionError(
                    f"Tool '{tool.name}' received undeclared arguments: "
                    f"{', '.join(unknown)}"
                )
        for key, value in arguments.items():
            property_schema = properties.get(key)
            if not isinstance(property_schema, dict):
                continue
            expected_type = property_schema.get("type")
            python_type = _JSON_TYPES.get(expected_type)
            if python_type and (
                not isinstance(value, python_type)
                or (expected_type == "integer" and isinstance(value, bool))
                or (expected_type == "number" and isinstance(value, bool))
            ):
                raise ToolExecutionError(
                    f"Tool '{tool.name}' argument '{key}' must be {expected_type}"
                )


@dataclass(frozen=True, slots=True)
class ToolExecutionRecord:
    tool_name: str
    success: bool
    result_type: str
    occurred_at: datetime
