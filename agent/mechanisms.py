from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

MECHANISM_TYPES = {
    "trading",
    "blogging",
    "freelancing",
    "automation_service",
    "digital_product",
    "lead_generation",
}


@dataclass
class IncomeMechanism:
    mechanism_id: int | None
    type: str
    title: str
    description: str
    expected_revenue: float
    expected_cost: float
    expected_token_cost: float
    automation_potential: float
    repeatability_score: float
    maintenance_cost: float
    current_stage: str
    status: str


@dataclass
class SurvivalScoreBreakdown:
    final_score: float
    net_value_estimate: float
    token_efficiency_score: float
    components: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_score": self.final_score,
            "net_value_estimate": self.net_value_estimate,
            "token_efficiency_score": self.token_efficiency_score,
            "components": self.components,
        }


class SurvivalScorer:
    """투자/비투자 수익 메커니즘 공통 생존 점수 계산기."""

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))

    @classmethod
    def score(
        cls,
        *,
        expected_revenue: float,
        expected_cost: float,
        expected_token_cost: float,
        automation_potential: float,
        repeatability_score: float,
        maintenance_cost: float,
        confidence_score: float,
        time_to_payout: float,
    ) -> SurvivalScoreBreakdown:
        net_value_estimate = expected_revenue - expected_cost - expected_token_cost - maintenance_cost
        token_efficiency_score = 0.0
        if expected_token_cost > 0:
            token_efficiency_score = net_value_estimate / expected_token_cost
        elif net_value_estimate > 0:
            token_efficiency_score = 1.0

        net_component = max(-1.0, min(2.0, net_value_estimate / max(abs(expected_revenue), 1.0)))
        token_component = max(-1.0, min(2.0, token_efficiency_score))
        automation_component = cls._clamp01(automation_potential)
        repeatability_component = cls._clamp01(repeatability_score)
        maintenance_component = 1.0 - cls._clamp01(maintenance_cost / max(expected_revenue, 1.0))
        confidence_component = cls._clamp01(confidence_score)
        payout_component = 1.0 - cls._clamp01(time_to_payout)

        final_score = (
            (net_component * 0.28)
            + (token_component * 0.16)
            + (automation_component * 0.15)
            + (repeatability_component * 0.14)
            + (maintenance_component * 0.10)
            + (confidence_component * 0.11)
            + (payout_component * 0.06)
        )

        return SurvivalScoreBreakdown(
            final_score=round(final_score, 6),
            net_value_estimate=round(net_value_estimate, 6),
            token_efficiency_score=round(token_efficiency_score, 6),
            components={
                "net_component": round(net_component, 6),
                "token_component": round(token_component, 6),
                "automation_component": round(automation_component, 6),
                "repeatability_component": round(repeatability_component, 6),
                "maintenance_component": round(maintenance_component, 6),
                "confidence_component": round(confidence_component, 6),
                "payout_component": round(payout_component, 6),
            },
        )


def mechanism_to_dict(mechanism: IncomeMechanism) -> dict[str, Any]:
    return asdict(mechanism)
