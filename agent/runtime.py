from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Iterable, Protocol

from .llm import LLMClient
from .models import AgentState, Opportunity, OpportunityType, Task, TaskStatus
from .persistence import SQLiteStore
from .strategy import StrategyEngine


class BrowserTool(Protocol):
    def run(self, instruction: str) -> str: ...


class ShellTool(Protocol):
    def run(self, command: str) -> str: ...


class BrokerTool(Protocol):
    def place_order(
        self,
        market: OpportunityType,
        symbol: str,
        budget: float,
        side: str | None = None,
        client_order_id: str | None = None,
    ) -> object: ...

    def get_order(self, market: OpportunityType, symbol: str, order_id: str) -> dict: ...

    def cancel_order(self, market: OpportunityType, symbol: str, order_id: str) -> dict: ...


@dataclass
class RuntimeConfig:
    max_cycles: int = 5
    max_single_trade_ratio: float = 0.35
    daily_loss_limit_ratio: float = 0.15


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
        store: SQLiteStore | None = None,
    ) -> None:
        self.strategy = strategy
        self.browser = browser
        self.shell = shell
        self.broker = broker
        self.config = config or RuntimeConfig()
        self.team = team
        self.store = store

    def run(self, state: AgentState, opportunities: Iterable[Opportunity]) -> AgentState:
        self.recover_pending_orders()
        queue = self.strategy.select(opportunities, state)
        cycle = 0

        while queue and cycle < self.config.max_cycles:
            if self._over_loss_limit(state):
                self._record_event("risk_halt", "Daily loss limit exceeded; stop execution")
                break

            task = queue.pop(0)
            cycle += 1

            assignee = self._select_assignee(task)
            self._execute_task(task, state, assignee)

        if self.store:
            self.store.snapshot_team_kpis()
        return state

    def recover_pending_orders(self) -> None:
        if not self.store:
            return
        for market, symbol, client_order_id in self.store.pending_order_intents():
            self._record_event(
                "recovery_pending_order",
                f"market={market};symbol={symbol};client_order_id={client_order_id}",
            )

    def _over_loss_limit(self, state: AgentState) -> bool:
        max_loss = state.starting_budget * self.config.daily_loss_limit_ratio
        return state.profit < -max_loss

    def _select_assignee(self, task: Task) -> str:
        if not self.team or not self.team.members:
            return "solo-agent"
        assigned = self.team.assign(task)
        return assigned.name

    def _execute_task(self, task: Task, state: AgentState, assignee: str) -> None:
        task.status = TaskStatus.RUNNING
        realized = 0.0

        try:
            max_trade_budget = state.starting_budget * self.config.max_single_trade_ratio
            if task.estimated_cost > max_trade_budget:
                raise ValueError(f"task budget exceeds limit: {task.estimated_cost:.2f} > {max_trade_budget:.2f}")

            research = self.browser.run(f"시장 검증: {task.title}")
            build_log = self.shell.run("워크플로 빌드 및 실행")

            broker_log = ""
            if task.channel in (OpportunityType.STOCK, OpportunityType.CRYPTO):
                broker_log = self._execute_order(task)
                self._record_position(task)

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
            self._record_event("task_done", f"task={task.title};assignee={assignee}")
        except Exception as exc:  # noqa: BLE001
            task.status = TaskStatus.FAILED
            task.notes = f"assignee={assignee}; error={exc}"
            state.failed_tasks.append(task)
            self._record_event("task_failed", f"task={task.title};assignee={assignee};error={exc}")
        finally:
            if self.store:
                self.store.record_task_run(task=task, assignee=assignee, realized_revenue=realized)

    def _execute_order(self, task: Task) -> str:
        side = "buy" if task.channel == OpportunityType.STOCK else "BUY"
        client_order_id = f"task-{task.id}-{uuid.uuid4().hex[:8]}"
        if self.store:
            self.store.record_order_intent(
                task_id=task.id,
                market=task.channel,
                symbol=task.instrument,
                side=side,
                budget=task.estimated_cost,
                client_order_id=client_order_id,
                status="submitted",
            )

        result = self.broker.place_order(
            market=task.channel,
            symbol=task.instrument,
            budget=task.estimated_cost,
            side=side,
            client_order_id=client_order_id,
        )

        if isinstance(result, str):
            status = "filled"
            order_id = client_order_id
            raw_response = result
            broker_name = "generic"
        else:
            status = getattr(result, "status", "submitted")
            order_id = str(getattr(result, "order_id", client_order_id))
            raw_response = str(getattr(result, "raw", result))
            broker_name = str(getattr(result, "broker", "generic"))

        if self.store:
            self.store.record_order_execution(
                client_order_id=client_order_id,
                broker=broker_name,
                order_id=order_id,
                status=status,
                raw_response=raw_response,
            )
            self.store.update_order_intent_status(client_order_id=client_order_id, status=status)

        return raw_response

    def _record_position(self, task: Task) -> None:
        if not self.store:
            return
        self.store.record_position(
            market=task.channel,
            symbol=task.instrument,
            budget=task.estimated_cost,
            side="buy",
            status="submitted",
            metadata=task.title,
        )

    def _record_event(self, event_type: str, details: str) -> None:
        if self.store:
            self.store.record_event(event_type, details)

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
    def place_order(
        self,
        market: OpportunityType,
        symbol: str,
        budget: float,
        side: str | None = None,
        client_order_id: str | None = None,
    ) -> str:
        ticker = symbol or "UNKNOWN"
        return (
            f"order_sent market={market.value} symbol={ticker} budget={budget:.2f} "
            f"side={side or 'buy'} client_order_id={client_order_id or 'none'}"
        )

    def get_order(self, market: OpportunityType, symbol: str, order_id: str) -> dict:
        return {"market": market.value, "symbol": symbol, "orderId": order_id, "status": "FILLED", "stub": True}

    def cancel_order(self, market: OpportunityType, symbol: str, order_id: str) -> dict:
        return {"market": market.value, "symbol": symbol, "orderId": order_id, "status": "CANCELED", "stub": True}


class MockBrowser:
    def run(self, instruction: str) -> str:
        return f"ok:{instruction}"


class MockShell:
    def run(self, command: str) -> str:
        return f"executed:{command}"
