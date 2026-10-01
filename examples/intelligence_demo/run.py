"""Run the synthetic CitrusCare Intelligence Engine workflow without a server."""

from __future__ import annotations

import asyncio
import json

from citruscare.intelligence import IntelligenceRequest, create_demo_orchestrator


async def main() -> None:
    orchestrator = create_demo_orchestrator()
    response = await orchestrator.run(
        IntelligenceRequest(
            query="Summarize the synthetic evidence note.",
            request_id="local-intelligence-demo",
        )
    )
    print(json.dumps(response.to_dict(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
