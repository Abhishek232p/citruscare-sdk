"""Call an OpenAI-compatible endpoint using CITRUSCARE_* environment settings."""

import asyncio
import os

from citruscare import Agent, Settings, ToolRegistry
from citruscare.providers import OpenAICompatibleProvider


async def main() -> None:
    if not os.getenv("CITRUSCARE_API_KEY"):
        raise SystemExit("Set CITRUSCARE_API_KEY before running this example.")
    provider = OpenAICompatibleProvider(Settings.from_env())
    result = await Agent(provider, ToolRegistry()).run(
        "Reply with a brief greeting."
    )
    print(result.content)


if __name__ == "__main__":
    asyncio.run(main())
