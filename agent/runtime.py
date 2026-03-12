from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Protocol

from .llm import LLMClient
from .models import AgentState, Opportunity, OpportunityType, Task, TaskStatus
from .strategy import StrategyEngine


class BrowserTool(Protocol):
    def run(self, instruction: str) -> str: ...


class ShellTool(Protocol):
    def run(self, command: str) -> str: ...


class BrokerTool(Protocol):
    def place_order(self, market: OpportunityType, symbol: str, budget: float) -> str: ...


@dataclass
class RuntimeConfig:
    max_cycles: int = 5


@dataclass
class SubAgent:
    """특정 시장/업무를 담당하는 서브 에이전트."""

    name: str
    specialties: set[OpportunityType] = field(default_factory=set)

    def can_handle(self, task: Task) -> bool:
        if not self.specialties:
            return True
        return task.channel in self.specialties


@dataclass
class AgentTeam:
    lead_name: str
    members: list[SubAgent]

    def assign(self, task: Task) -> SubAgent:
        for member in self.members:
            if member.can_handle(task):
                return member
        return self.members[0]


class AgentRuntime:
    """실행-평가-계획 루프를 수행하는 런타임."""

    def __init__(
        self,
        strategy: StrategyEngine,
        browser: BrowserTool,
        shell: ShellTool,
        broker: BrokerTool,
        config: RuntimeConfig | None = None,
        team: AgentTeam | None = None,
    ) -> None:
        self.strategy = strategy
        self.browser = browser
        self.shell = shell
        self.broker = broker
        self.config = config or RuntimeConfig()
        self.team = team

    def run(self, state: AgentState, opportunities: Iterable[Opportunity]) -> AgentState:
        queue = self.strategy.select(opportunities, state)
        cycle = 0

        while queue and cycle < self.config.max_cycles:
            task = queue.pop(0)
            cycle += 1

            assignee = self._select_assignee(task)
            self._execute_task(task, state, assignee)

        return state

    def _select_assignee(self, task: Task) -> str:
        if not self.team or not self.team.members:
            return "solo-agent"
        assigned = self.team.assign(task)
        return assigned.name

    def _execute_task(self, task: Task, state: AgentState, assignee: str) -> None:
        task.status = TaskStatus.RUNNING
        try:
            research = self.browser.run(f"시장 검증: {task.title}")
            build_log = self.shell.run("워크플로 빌드 및 실행")

            broker_log = ""
            if task.channel in (OpportunityType.STOCK, OpportunityType.CRYPTO):
                broker_log = self.broker.place_order(task.channel, task.instrument, task.estimated_cost)

            task.notes = (
                f"assignee={assignee}; research={research}; build={build_log}; broker={broker_log}"
            )

            state.cash -= task.estimated_cost
            state.cost += task.estimated_cost

            realized = self._realize_revenue(task)
            state.cash += realized
            state.revenue += realized

            task.status = TaskStatus.DONE
            state.completed_tasks.append(task)
        except Exception as exc:  # noqa: BLE001
            task.status = TaskStatus.FAILED
            task.notes = f"assignee={assignee}; error={exc}"
            state.failed_tasks.append(task)

    def _realize_revenue(self, task: Task) -> float:
        if task.channel == OpportunityType.BUSINESS:
            return task.expected_revenue * 0.8
        if task.channel == OpportunityType.STOCK:
            return task.expected_revenue * 0.65
        return task.expected_revenue * 0.6


class LLMBrowser:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def run(self, instruction: str) -> str:
        prompt = (
            "다음 사업 기회에 대해 웹 리서치 가설과 검증 체크리스트 3개를 간단히 작성해줘. "
            f"instruction={instruction}"
        )
        return self._llm.complete(prompt)


class LLMShell:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    def run(self, command: str) -> str:
        prompt = (
            "다음 목표를 자동화하기 위한 안전한 셸 실행 계획을 3단계 bullet로 작성해줘. "
            f"goal={command}"
        )
        return self._llm.complete(prompt)


class MockBroker:
    def place_order(self, market: OpportunityType, symbol: str, budget: float) -> str:
        ticker = symbol or "UNKNOWN"
        return f"order_sent market={market.value} symbol={ticker} budget={budget:.2f}"


class MockBrowser:
    def run(self, instruction: str) -> str:
        return f"ok:{instruction}"


class MockShell:
    def run(self, command: str) -> str:
        return f"executed:{command}"
