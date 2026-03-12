from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List


class TaskStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class OpportunityType(str, Enum):
    BUSINESS = "business"
    STOCK = "stock"
    CRYPTO = "crypto"


@dataclass
class Opportunity:
    name: str
    description: str
    required_budget: float
    expected_return: float
    risk_score: float  # 0.0(low) ~ 1.0(high)
    opportunity_type: OpportunityType = OpportunityType.BUSINESS
    symbol: str = ""


@dataclass
class Task:
    id: int
    title: str
    action_plan: List[str]
    estimated_cost: float
    expected_revenue: float
    channel: OpportunityType = OpportunityType.BUSINESS
    instrument: str = ""
    status: TaskStatus = TaskStatus.QUEUED
    notes: str = ""


@dataclass
class AgentState:
    starting_budget: float
    cash: float
    revenue: float = 0.0
    cost: float = 0.0
    completed_tasks: List[Task] = field(default_factory=list)
    failed_tasks: List[Task] = field(default_factory=list)

    @property
    def profit(self) -> float:
        return self.revenue - self.cost

    @property
    def roi(self) -> float:
        if self.starting_budget == 0:
            return 0.0
        return self.profit / self.starting_budget
