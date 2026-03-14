from __future__ import annotations

from dataclasses import dataclass

from .persistence import SQLiteStore

AUTOMATION_CANDIDATE_TYPES = {
    "workflow_automation",
    "productized_automation",
    "token_optimized",
    "manual_watch",
}


@dataclass(frozen=True)
class CandidateTransition:
    current: str
    target: str
    reason: str


TRANSITIONS = {
    "proposed": {"approve": "evaluating", "reject": "retired"},
    "evaluating": {"activate": "active", "pause": "paused", "reject": "retired"},
    "active": {"pause": "paused", "retire": "retired"},
    "paused": {"resume": "active", "retire": "retired"},
    "retired": {},
}


class AutomationCandidateDetector:
    """Detects automation candidates from mechanism/blueprint registry."""

    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    @staticmethod
    def classify_candidate_type(mechanism_type: str, automation_potential: float, repeatability_score: float) -> str:
        m = mechanism_type.strip().lower()
        if m in {"automation_service", "digital_product"}:
            return "productized_automation"
        if automation_potential >= 0.75 and repeatability_score >= 0.7:
            return "workflow_automation"
        if automation_potential >= 0.5:
            return "token_optimized"
        return "manual_watch"

    def detect(self) -> int:
        created = 0
        for mechanism in self.store.list_income_mechanisms(limit=200):
            mechanism_id = int(mechanism[0])
            mechanism_type = str(mechanism[1])
            title = str(mechanism[2])
            automation_potential = float(mechanism[7])
            repeatability_score = float(mechanism[8])
            status = str(mechanism[11]).lower()
            if status not in {"active", "testing"}:
                continue

            candidate_type = self.classify_candidate_type(mechanism_type, automation_potential, repeatability_score)
            confidence = min(0.95, 0.35 + (automation_potential * 0.35) + (repeatability_score * 0.3))
            reason = (
                f"mechanism={mechanism_type}; automation={automation_potential:.2f}; "
                f"repeatability={repeatability_score:.2f}"
            )
            self.store.upsert_automation_candidate(
                mechanism_id=mechanism_id,
                candidate_type=candidate_type,
                title=f"{title} automation candidate",
                status="proposed",
                confidence_score=confidence,
                reason=reason,
            )
            created += 1
        return created


def apply_candidate_transition(current_status: str, action: str) -> CandidateTransition:
    current = current_status.strip().lower()
    next_status = TRANSITIONS.get(current, {}).get(action.strip().lower())
    if not next_status:
        raise ValueError(f"invalid transition: status={current_status}, action={action}")
    return CandidateTransition(current=current, target=next_status, reason=f"action={action}")
