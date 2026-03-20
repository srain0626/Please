from __future__ import annotations

from dataclasses import dataclass

from .persistence import SQLiteStore


@dataclass
class AllocationScoreBreakdown:
    key: str
    score: float
    conversion_rate: float
    response_rate: float
    estimated_revenue: float
    revenue_per_token: float
    failure_rate: float
    no_response_rate: float
    repeatability_score: float
    automation_potential: float
    execution_cost: float
    token_cost: float


class AllocationScoringEngine:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def score_dimension(self, dimension: str, limit: int = 100) -> list[AllocationScoreBreakdown]:
        rows = self.store.performance_summary(dimension=dimension, limit=limit)
        scored: list[AllocationScoreBreakdown] = []
        for row in rows:
            (
                key,
                _submissions,
                _deliveries,
                _responses,
                _conversions,
                estimated_revenue,
                response_rate,
                conversion_rate,
                _revenue_per_run,
                revenue_per_token,
                _conversion_per_token,
                failure_rate,
                no_response_rate,
                repeatability_score,
                automation_potential,
                execution_cost,
                token_cost,
            ) = row

            score = (
                (conversion_rate * 0.24)
                + (response_rate * 0.12)
                + (min(1.0, estimated_revenue / 200.0) * 0.12)
                + (min(1.0, max(0.0, revenue_per_token / 5.0)) * 0.16)
                + (repeatability_score * 0.10)
                + (automation_potential * 0.08)
                - (failure_rate * 0.09)
                - (no_response_rate * 0.06)
                - (min(1.0, execution_cost / 300.0) * 0.02)
                - (min(1.0, token_cost / 1000.0) * 0.01)
            )

            scored.append(
                AllocationScoreBreakdown(
                    key=key,
                    score=round(score, 6),
                    conversion_rate=conversion_rate,
                    response_rate=response_rate,
                    estimated_revenue=estimated_revenue,
                    revenue_per_token=revenue_per_token,
                    failure_rate=failure_rate,
                    no_response_rate=no_response_rate,
                    repeatability_score=repeatability_score,
                    automation_potential=automation_potential,
                    execution_cost=execution_cost,
                    token_cost=token_cost,
                )
            )
        return sorted(scored, key=lambda x: x.score, reverse=True)


class AllocationOptimizer:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store
        self.scorer = AllocationScoringEngine(store)

    def generate_recommendations(self) -> int:
        created = 0

        # channel allocation adjustments
        for score in self.scorer.score_dimension("channel", limit=50):
            channel_id = int(score.key) if score.key.isdigit() else None
            if channel_id is None:
                continue
            if score.conversion_rate == 0 and score.no_response_rate > 0.6:
                self.store.record_allocation_recommendation(
                    mechanism_id=None,
                    channel_id=channel_id,
                    target_type=None,
                    variant_id=None,
                    recommendation_type="pause_channel",
                    rationale="zero conversion and high no_response_rate",
                    expected_impact=-0.1,
                    confidence=0.7,
                    status="auto_applied",
                    auto_applied=True,
                )
                created += 1
                continue
            if score.revenue_per_token > 1.5 and score.conversion_rate > 0:
                self.store.record_allocation_recommendation(
                    mechanism_id=None,
                    channel_id=channel_id,
                    target_type=None,
                    variant_id=None,
                    recommendation_type="increase_allocation",
                    rationale="high revenue_per_token and conversion",
                    expected_impact=0.2,
                    confidence=0.75,
                    status="pending",
                )
                created += 1
            if score.failure_rate > 0.5:
                self.store.record_allocation_recommendation(
                    mechanism_id=None,
                    channel_id=channel_id,
                    target_type=None,
                    variant_id=None,
                    recommendation_type="decrease_allocation",
                    rationale="failure_rate above threshold",
                    expected_impact=-0.15,
                    confidence=0.68,
                    status="auto_applied",
                    auto_applied=True,
                )
                created += 1

        # variant promotions/retirements
        for score in self.scorer.score_dimension("variant", limit=100):
            if score.key == "none":
                continue
            variant_id = int(score.key)
            if score.conversion_rate > 0.2 or score.revenue_per_token > 2.0:
                self.store.record_allocation_recommendation(
                    mechanism_id=None,
                    channel_id=None,
                    target_type=None,
                    variant_id=variant_id,
                    recommendation_type="promote_variant",
                    rationale="variant shows strong conversion efficiency",
                    expected_impact=0.2,
                    confidence=0.73,
                    status="pending",
                )
                created += 1
            elif score.no_response_rate > 0.7 or score.failure_rate > 0.6:
                self.store.record_allocation_recommendation(
                    mechanism_id=None,
                    channel_id=None,
                    target_type=None,
                    variant_id=variant_id,
                    recommendation_type="retire_variant",
                    rationale="variant underperforming in response/failure metrics",
                    expected_impact=-0.12,
                    confidence=0.69,
                    status="auto_applied",
                    auto_applied=True,
                )
                created += 1

        # execution mode switch recommendation
        mode_scores = self.scorer.score_dimension("execution_mode", limit=20)
        if len(mode_scores) >= 2:
            top_mode = mode_scores[0]
            low_mode = mode_scores[-1]
            if top_mode.score - low_mode.score > 0.12:
                self.store.record_allocation_recommendation(
                    mechanism_id=None,
                    channel_id=None,
                    target_type=None,
                    variant_id=None,
                    recommendation_type="switch_execution_mode",
                    rationale=f"prefer mode={top_mode.key} over mode={low_mode.key} from allocation score gap",
                    expected_impact=0.1,
                    confidence=0.66,
                    status="pending",
                )
                created += 1

        self._integrate_mechanism_feedback()
        return created

    def _integrate_mechanism_feedback(self) -> None:
        for score in self.scorer.score_dimension("mechanism", limit=100):
            if not score.key.isdigit():
                continue
            mechanism_id = int(score.key)
            if score.score > 0.2:
                self.store.apply_distribution_feedback(mechanism_id, confidence_delta=0.03, repeatability_delta=0.02)
            elif score.score < -0.08:
                self.store.apply_distribution_feedback(mechanism_id, confidence_delta=-0.03, repeatability_delta=-0.02)
