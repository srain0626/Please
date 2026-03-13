from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import AgentState, Opportunity, OpportunityType
from .persistence import SQLiteStore


@dataclass
class LabConfig:
    exploratory_budget_ratio: float = 0.15
    validated_budget_ratio: float = 0.55
    max_experiments_per_cycle: int = 4
    confidence_increase_success: float = 0.12
    confidence_decrease_fail: float = 0.18
    validated_threshold: float = 0.75
    rejected_threshold: float = 0.3
    min_experiments_for_validation: int = 2
    fallback_promote_top_testing: bool = True
    fallback_max_promotions: int = 1


class OpportunityFactory:
    """기회 생성기: 시장 시그널 + 내부 반복 패턴 기반 기회 생성."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def market_signal_opportunities(self) -> list[Opportunity]:
        events = list(self.store.recent_events(limit=50))
        boost = 0.0
        for _, event_type, details, _ in events:
            lowered = f"{event_type} {details}".lower()
            if "order_validation_corrected" in lowered:
                boost += 0.02
            if "order_validation_failed" in lowered:
                boost -= 0.03
            if "task_done" in lowered:
                boost += 0.01

        risk = min(0.75, max(0.2, 0.45 - boost))
        expected = 180.0 + (boost * 100)
        return [
            Opportunity(
                name="Signal: BTC 변동성 돌파",
                description="이벤트 기반 변동성 신호를 활용한 소액 추세 추종",
                required_budget=60.0,
                expected_return=max(90.0, expected),
                risk_score=risk,
                opportunity_type=OpportunityType.CRYPTO,
                symbol="BTC-USDT",
                confidence_score=0.45,
                evidence_score=0.5,
                execution_complexity=0.45,
                repeatability_score=0.65,
                time_to_payout=0.5,
            )
        ]

    def recurring_internal_opportunities(self) -> list[Opportunity]:
        patterns = self.store.recent_success_patterns(limit=5)
        generated: list[Opportunity] = []
        for channel, instrument, avg_cost, avg_revenue in patterns:
            if avg_revenue <= avg_cost:
                continue
            confidence = min(0.85, 0.5 + ((avg_revenue - avg_cost) / max(avg_cost, 1.0)) * 0.2)
            generated.append(
                Opportunity(
                    name=f"Recurring: {channel}-{instrument or 'GENERIC'}",
                    description="과거 성공 실행 패턴 재활용",
                    required_budget=max(20.0, float(avg_cost) * 0.7),
                    expected_return=max(25.0, float(avg_revenue) * 0.8),
                    risk_score=0.35 if channel != "business" else 0.3,
                    opportunity_type=OpportunityType(channel),
                    symbol=instrument or "",
                    confidence_score=confidence,
                    evidence_score=0.7,
                    execution_complexity=0.4,
                    repeatability_score=0.75,
                    time_to_payout=0.6,
                )
            )
        return generated

    def generate(self, seed_opportunities: Iterable[Opportunity]) -> list[Opportunity]:
        seen: set[tuple[str, str]] = set()
        merged: list[Opportunity] = []

        for op in list(seed_opportunities) + self.market_signal_opportunities() + self.recurring_internal_opportunities():
            key = (op.name, op.symbol)
            if key in seen:
                continue
            seen.add(key)
            merged.append(op)
        return merged


class StrategyLab:
    """가설/실험 루프를 수행하고 validated 기회만 승격한다."""

    def __init__(self, store: SQLiteStore, config: LabConfig | None = None) -> None:
        self.store = store
        self.config = config or LabConfig()
        self.factory = OpportunityFactory(store)

    @staticmethod
    def _opportunity_key(op: Opportunity) -> str:
        return f"{op.opportunity_type.value}:{op.symbol}:{op.name}"

    @staticmethod
    def _classify_failure(result_return_pct: float, allocated_budget: float, required_budget: float) -> str:
        if result_return_pct < -0.15:
            return "invalidated_by_loss"
        if allocated_budget < required_budget * 0.5:
            return "high_execution_cost"
        if result_return_pct < 0:
            return "insufficient_edge"
        return "low_confidence"

    def _simulate_experiment_return(self, op: Opportunity) -> float:
        edge = op.expected_edge
        confidence = op.confidence_score
        penalty = (op.risk_score * 0.45) + (op.execution_complexity * 0.2)
        bonus = (op.evidence_score * 0.2) + (op.repeatability_score * 0.15)
        return round(edge + (confidence * 0.1) + bonus - penalty, 4)

    def _adaptive_confidence_update(self, *, hypothesis_id: int, current_conf: float, latest_return_pct: float) -> float:
        exp_count, win_count, avg_return = self.store.hypothesis_experiment_stats(hypothesis_id)
        win_rate = (win_count / exp_count) if exp_count > 0 else 0.0
        avg_return_score = max(-1.0, min(1.0, avg_return))
        momentum = (latest_return_pct * 0.35) + (avg_return_score * 0.25) + ((win_rate - 0.5) * 0.2)
        updated = current_conf + momentum
        return max(0.0, min(1.0, updated))

    def research_and_promote(self, state: AgentState, seed_opportunities: Iterable[Opportunity]) -> list[Opportunity]:
        opportunities = self.factory.generate(seed_opportunities)

        exploratory_budget_total = state.starting_budget * self.config.exploratory_budget_ratio
        per_experiment_budget = max(10.0, exploratory_budget_total / max(1, self.config.max_experiments_per_cycle))

        for op in opportunities:
            linked_key = self._opportunity_key(op)
            hypo_id = self.store.upsert_hypothesis(
                title=op.name,
                thesis=op.description,
                evidence=f"symbol={op.symbol or 'N/A'}; type={op.opportunity_type.value}",
                expected_edge=op.expected_edge,
                confidence_score=op.confidence_score,
                invalidation_rule="3회 연속 음수 수익률 또는 confidence<0.3",
                status="proposed",
                linked_opportunity_key=linked_key,
            )
            self.store.record_event("hypothesis_proposed", f"hypothesis_id={hypo_id};key={linked_key}")

        candidates = self.store.list_hypotheses(statuses=["proposed", "testing"], limit=self.config.max_experiments_per_cycle)

        for hypothesis in candidates:
            hypo_id = int(hypothesis[0])
            linked_key = str(hypothesis[8])
            op = next((x for x in opportunities if self._opportunity_key(x) == linked_key), None)
            if op is None:
                continue

            result_return_pct = self._simulate_experiment_return(op)
            allocated_budget = min(per_experiment_budget, op.required_budget)
            pnl = allocated_budget * result_return_pct
            outcome = "success" if result_return_pct > 0 else "failure"
            failure_reason = ""
            notes = "auto lab experiment"

            current_conf = float(hypothesis[5])
            if outcome == "success":
                current_conf = min(1.0, current_conf + self.config.confidence_increase_success)
            else:
                current_conf = max(0.0, current_conf - self.config.confidence_decrease_fail)
                failure_reason = self._classify_failure(result_return_pct, allocated_budget, op.required_budget)
                notes += f"; failure_reason={failure_reason}"

            self.store.record_experiment_run(
                hypothesis_id=hypo_id,
                allocated_budget=allocated_budget,
                result_pnl=pnl,
                result_return_pct=result_return_pct,
                outcome=outcome,
                failure_reason=failure_reason,
                notes=notes,
            )

            next_conf = self._adaptive_confidence_update(
                hypothesis_id=hypo_id,
                current_conf=current_conf,
                latest_return_pct=result_return_pct,
            )

            exp_count, _, _ = self.store.hypothesis_experiment_stats(hypo_id)
            next_status = "testing"
            if next_conf >= self.config.validated_threshold and exp_count >= self.config.min_experiments_for_validation:
                next_status = "validated"
            elif next_conf <= self.config.rejected_threshold:
                next_status = "rejected"

            self.store.update_hypothesis_state(hypothesis_id=hypo_id, confidence_score=next_conf, status=next_status)
            self.store.record_event(
                "experiment_completed",
                (
                    f"hypothesis_id={hypo_id};outcome={outcome};return_pct={result_return_pct:.4f};"
                    f"status={next_status};confidence={next_conf:.4f};exp_count={exp_count}"
                ),
            )

        self.store.archive_old_rejected_hypotheses(min_experiments=3)

        validated = self.store.list_hypotheses(statuses=["validated"], limit=50)
        promoted: list[Opportunity] = []
        for row in validated:
            linked_key = str(row[8])
            op = next((x for x in opportunities if self._opportunity_key(x) == linked_key), None)
            if op:
                promoted.append(op)

        if not promoted and self.config.fallback_promote_top_testing:
            fallback = self.store.list_hypotheses(statuses=["testing"], limit=self.config.fallback_max_promotions)
            for row in fallback:
                linked_key = str(row[8])
                op = next((x for x in opportunities if self._opportunity_key(x) == linked_key), None)
                if op:
                    promoted.append(op)
            if promoted:
                self.store.record_event("fallback_promotion", f"count={len(promoted)}")

        validated_budget_cap = state.starting_budget * self.config.validated_budget_ratio
        total_budget = 0.0
        budgeted: list[Opportunity] = []
        for op in promoted:
            if total_budget + op.required_budget > validated_budget_cap:
                continue
            total_budget += op.required_budget
            budgeted.append(op)
        return budgeted
