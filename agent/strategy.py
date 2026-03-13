from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from .models import AgentState, Opportunity, OpportunityType, Task


@dataclass
class RiskPolicy:
    max_risk_score: float = 0.5
    reserve_ratio: float = 0.2


class StrategyEngine:
    """Conway Research Automaton 스타일 기회 선택 엔진 (다요인 스코어링)."""

    def __init__(self, policy: RiskPolicy | None = None) -> None:
        self.policy = policy or RiskPolicy()

    def score(self, op: Opportunity) -> float:
        # 각 요소를 0~1 유사 범위로 정규화한 단순 가중치 모델.
        edge_score = max(-1.0, min(2.0, op.expected_edge))
        budget_efficiency = 1.0 / (1.0 + (op.required_budget / 300.0))
        risk_component = 1.0 - max(0.0, min(1.0, op.risk_score))
        confidence = max(0.0, min(1.0, op.confidence_score))
        evidence = max(0.0, min(1.0, op.evidence_score))
        complexity_component = 1.0 - max(0.0, min(1.0, op.execution_complexity))
        repeatability = max(0.0, min(1.0, op.repeatability_score))
        payout_speed = 1.0 - max(0.0, min(1.0, op.time_to_payout))

        return (
            (edge_score * 0.24)
            + (budget_efficiency * 0.10)
            + (risk_component * 0.14)
            + (confidence * 0.18)
            + (evidence * 0.10)
            + (complexity_component * 0.08)
            + (repeatability * 0.10)
            + (payout_speed * 0.06)
        )

    def select(self, opportunities: Iterable[Opportunity], state: AgentState) -> List[Task]:
        reserve_cash = state.starting_budget * self.policy.reserve_ratio
        usable_cash = max(0.0, state.cash - reserve_cash)

        ranked = sorted(opportunities, key=self.score, reverse=True)

        tasks: List[Task] = []
        for idx, op in enumerate(ranked, start=1):
            if op.risk_score > self.policy.max_risk_score:
                continue
            if op.required_budget > usable_cash:
                continue

            task = Task(
                id=idx,
                title=f"{op.name} 실행",
                action_plan=self._build_action_plan(op),
                estimated_cost=op.required_budget,
                expected_revenue=op.expected_return,
                channel=op.opportunity_type,
                instrument=op.symbol,
                notes=(
                    f"score={self.score(op):.4f};confidence={op.confidence_score:.2f};"
                    f"evidence={op.evidence_score:.2f};edge={op.expected_edge:.4f}"
                ),
            )
            tasks.append(task)
            usable_cash -= op.required_budget
        return tasks

    def _build_action_plan(self, op: Opportunity) -> List[str]:
        if op.opportunity_type == OpportunityType.STOCK:
            return [
                "종목 펀더멘털/모멘텀 점검",
                "분할 매수/손절 기준 설정",
                "시장가/지정가 주문 실행",
                "포지션 모니터링 및 리밸런싱",
            ]
        if op.opportunity_type == OpportunityType.CRYPTO:
            return [
                "온체인/거래량 시그널 점검",
                "포지션 사이즈와 손실 한도 계산",
                "거래소 주문 실행",
                "변동성 기반 재진입/청산",
            ]

        return [
            "시장 조사 및 수요 검증",
            "랜딩 페이지/자동화 파이프라인 구축",
            "캠페인 실행 및 전환율 측정",
            "성과 데이터 기반 반복 개선",
        ]
