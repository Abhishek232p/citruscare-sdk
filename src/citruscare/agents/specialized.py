"""Specialized task facades that share the common intelligence runtime."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Protocol

from citruscare.intelligence.orchestrator import (
    AgentOrchestrator,
    IntelligenceRequest,
    IntelligenceResponse,
    TaskType,
)


class TaskAgent(Protocol):
    name: str
    task: TaskType

    async def run(self, request: IntelligenceRequest) -> IntelligenceResponse: ...


@dataclass(slots=True)
class SharedRuntimeAgent:
    runtime: AgentOrchestrator
    name: str
    task: TaskType

    async def run(self, request: IntelligenceRequest) -> IntelligenceResponse:
        return await self.runtime.run(replace(request, task=self.task))


class ResearchAgent(SharedRuntimeAgent):
    def __init__(self, runtime: AgentOrchestrator) -> None:
        super().__init__(runtime, "research", TaskType.EVIDENCE_SEARCH)


class EvidenceAgent(SharedRuntimeAgent):
    def __init__(self, runtime: AgentOrchestrator) -> None:
        super().__init__(runtime, "evidence", TaskType.EVIDENCE_SEARCH)


class DocumentationAgent(SharedRuntimeAgent):
    def __init__(self, runtime: AgentOrchestrator) -> None:
        super().__init__(runtime, "documentation", TaskType.DOCUMENTATION_ASSISTANCE)


class MedicationInformationAgent(SharedRuntimeAgent):
    def __init__(self, runtime: AgentOrchestrator) -> None:
        super().__init__(
            runtime, "medication_information", TaskType.MEDICATION_INFORMATION
        )


class PatientContextAgent(SharedRuntimeAgent):
    def __init__(self, runtime: AgentOrchestrator) -> None:
        super().__init__(runtime, "patient_context", TaskType.PATIENT_CONTEXT_SUMMARY)


@dataclass(frozen=True, slots=True)
class AgentExecutionBudget:
    max_steps: int = 4
    max_tool_calls: int = 4
    timeout_seconds: float = 30.0
    budget_units: float = 1.0

    def __post_init__(self) -> None:
        if self.max_steps < 1 or self.max_tool_calls < 0:
            raise ValueError("agent step and tool budgets are invalid")
        if self.timeout_seconds <= 0 or self.budget_units <= 0:
            raise ValueError("agent timeout and budget must be positive")


class MultiAgentOrchestrator:
    """Selects one approved task agent; no recursive or autonomous delegation."""

    def __init__(
        self,
        runtime: AgentOrchestrator,
        budget: AgentExecutionBudget | None = None,
    ) -> None:
        self.runtime = runtime
        self.budget = budget or AgentExecutionBudget()
        self._agents: dict[str, TaskAgent] = {
            "research": ResearchAgent(runtime),
            "evidence": EvidenceAgent(runtime),
            "documentation": DocumentationAgent(runtime),
            "medication_information": MedicationInformationAgent(runtime),
            "patient_context": PatientContextAgent(runtime),
        }

    def plan(self, task: TaskType) -> TaskAgent:
        names = {
            TaskType.EVIDENCE_SEARCH: "research",
            TaskType.CLINICAL_SUMMARY: "evidence",
            TaskType.DOCUMENTATION_ASSISTANCE: "documentation",
            TaskType.MEDICATION_INFORMATION: "medication_information",
            TaskType.PATIENT_CONTEXT_SUMMARY: "patient_context",
        }
        selected = names.get(task, "evidence")
        return self._agents[selected]

    def _check_budget(self) -> None:
        if self.budget.max_steps < 1:
            raise RuntimeError("agent execution step budget exhausted")
        if self.budget.max_tool_calls < 1:
            raise RuntimeError("agent tool-call budget exhausted")
        if self.budget.budget_units < 1:
            raise RuntimeError("agent model-call budget exhausted")

    async def run(self, request: IntelligenceRequest) -> IntelligenceResponse:
        self._check_budget()
        selected = self.plan(request.task)
        return await asyncio.wait_for(
            selected.run(request), timeout=self.budget.timeout_seconds
        )

    async def research(self, request: IntelligenceRequest) -> IntelligenceResponse:
        self._check_budget()
        agent = self._agents["research"]
        return await asyncio.wait_for(
            agent.run(request), timeout=self.budget.timeout_seconds
        )
