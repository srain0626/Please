from __future__ import annotations

import json
from dataclasses import dataclass

from .persistence import SQLiteStore


@dataclass
class GeneratedVariantCandidate:
    target_id: int
    mechanism_id: int
    variant_key: str
    title: str
    payload_patch_json: str
    mutation_type: str
    rationale: str
    expected_note: str


@dataclass
class VariantComparison:
    incumbent_variant_id: int
    challenger_variant_id: int
    incumbent_score: float
    challenger_score: float
    score_delta: float
    min_trials_guard: bool
    small_sample_penalty: float
    rationale: str


class VariantGenerator:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    def generate_for_target(self, target_id: int, *, limit: int = 5) -> list[GeneratedVariantCandidate]:
        targets = [t for t in self.store.list_distribution_targets(limit=500) if int(t[0]) == target_id]
        if not targets:
            return []
        target = targets[0]
        mechanism_id = int(target[1])
        target_type = str(target[4])
        title = str(target[5])

        base_variants = self.store.list_offer_variants(target_id=target_id, limit=20)
        base_key = base_variants[0][2] if base_variants else "base"
        payload = {"source": base_key, "target_type": target_type}

        mutations = [
            ("headline_mutation", "headline_power_words", f"{title} - Fast Win"),
            ("cta_mutation", "cta_direct", f"{title} - Book Today"),
            ("length_mutation_short", "short_form", f"{title} - Quick Summary"),
            ("length_mutation_long", "long_form", f"{title} - Full Breakdown"),
            ("structure_mutation", "problem_solution", f"{title} - Problem/Solution"),
            ("execution_mode_mutation", "template_first", f"{title} - Template Assisted"),
        ]

        created: list[GeneratedVariantCandidate] = []
        for idx, (mutation_type, key_suffix, new_title) in enumerate(mutations[:limit], start=1):
            payload_patch = dict(payload)
            payload_patch.update(
                {
                    "mutation_type": mutation_type,
                    "cta_style": "direct" if "cta" in mutation_type else "soft",
                    "length": "short" if "short" in mutation_type else ("long" if "long" in mutation_type else "medium"),
                    "structure": "problem-solution" if "structure" in mutation_type else "feature-benefit",
                    "execution_hint": "template-first" if "execution" in mutation_type else "standard",
                }
            )
            created.append(
                GeneratedVariantCandidate(
                    target_id=target_id,
                    mechanism_id=mechanism_id,
                    variant_key=f"gen_{key_suffix}_{idx}",
                    title=new_title,
                    payload_patch_json=json.dumps(payload_patch, ensure_ascii=False),
                    mutation_type=mutation_type,
                    rationale=f"Generated from target_type={target_type} using {mutation_type}",
                    expected_note="challenger variant for small-batch experiment",
                )
            )
        return created


class VariantPerformanceComparator:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    @staticmethod
    def _score(metrics: tuple, small_sample_penalty: float) -> float:
        submissions, response_rate, conversion_rate, revenue, revenue_per_token, failure_rate, no_response_rate, token_cost = metrics
        revenue_component = min(1.0, revenue / 200.0)
        token_component = min(1.0, max(0.0, revenue_per_token / 5.0))
        cost_penalty = min(1.0, token_cost / 1000.0)
        return (
            (conversion_rate * 0.30)
            + (response_rate * 0.12)
            + (revenue_component * 0.14)
            + (token_component * 0.14)
            - (failure_rate * 0.12)
            - (no_response_rate * 0.10)
            - (cost_penalty * 0.05)
            - small_sample_penalty
        )

    def compare(self, incumbent_variant_id: int, challenger_variant_id: int, *, min_trials: int = 3) -> VariantComparison:
        incumbent_metrics = self.store.variant_metrics(incumbent_variant_id)
        challenger_metrics = self.store.variant_metrics(challenger_variant_id)

        incumbent_submissions = int(incumbent_metrics[0])
        challenger_submissions = int(challenger_metrics[0])
        min_trials_guard = incumbent_submissions < min_trials or challenger_submissions < min_trials
        small_sample_penalty = 0.12 if min_trials_guard else 0.0

        incumbent_score = self._score(incumbent_metrics, small_sample_penalty=0.0)
        challenger_score = self._score(challenger_metrics, small_sample_penalty=small_sample_penalty)

        return VariantComparison(
            incumbent_variant_id=incumbent_variant_id,
            challenger_variant_id=challenger_variant_id,
            incumbent_score=round(incumbent_score, 6),
            challenger_score=round(challenger_score, 6),
            score_delta=round(challenger_score - incumbent_score, 6),
            min_trials_guard=min_trials_guard,
            small_sample_penalty=small_sample_penalty,
            rationale=(
                f"incumbent_trials={incumbent_submissions}; challenger_trials={challenger_submissions}; "
                f"min_trials_guard={min_trials_guard}; penalty={small_sample_penalty:.2f}"
            ),
        )


class OfferSelfImprovementLoop:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store
        self.generator = VariantGenerator(store)
        self.comparator = VariantPerformanceComparator(store)

    def run(
        self,
        *,
        max_new_variants_per_target: int = 2,
        max_testing_per_target: int = 3,
        max_generated_per_mechanism_window: int = 12,
        lookback_hours: int = 24,
        min_mechanism_confidence: float = 0.4,
        max_token_budget: float = 120.0,
    ) -> int:
        created = 0
        targets = self.store.list_distribution_targets(limit=100)
        for target in targets:
            target_id = int(target[0])
            mechanism_id = int(target[1])
            target_type = str(target[4])
            block_reason = self.store.variant_generation_block_reason(
                mechanism_id=mechanism_id,
                target_id=target_id,
                max_testing_per_target=max_testing_per_target,
                max_generated_per_mechanism_window=max_generated_per_mechanism_window,
                lookback_hours=lookback_hours,
                min_mechanism_confidence=min_mechanism_confidence,
                max_token_budget=max_token_budget,
            )
            if block_reason:
                self.store.record_creative_recommendation(
                    mechanism_id=mechanism_id,
                    target_type=target_type,
                    variant_id=None,
                    blueprint_id=None,
                    asset_id=None,
                    recommendation_type="update_blueprint_default",
                    rationale=f"generation blocked by safety cap: {block_reason}",
                    expected_impact=0.0,
                    confidence=0.55,
                    status="blocked",
                )
                continue

            generated = self.generator.generate_for_target(target_id, limit=max_new_variants_per_target)
            for candidate in generated:
                variant_id = self.store.create_offer_variant(
                    target_id=candidate.target_id,
                    variant_key=candidate.variant_key,
                    title=candidate.title,
                    payload_patch_json=candidate.payload_patch_json,
                    status="proposed",
                )
                self.store.enqueue_variant_experiment(
                    variant_id=variant_id,
                    target_id=candidate.target_id,
                    mechanism_id=candidate.mechanism_id,
                    channel_id=None,
                    planned_trial_count=2,
                    max_trial_count=5,
                    priority=0.5,
                    status="queued",
                )
                self.store.record_creative_recommendation(
                    mechanism_id=mechanism_id,
                    target_type=target_type,
                    variant_id=variant_id,
                    blueprint_id=None,
                    asset_id=None,
                    recommendation_type="change_default_headline_style" if "headline" in candidate.mutation_type else "revise_structure",
                    rationale=f"{candidate.rationale}; note={candidate.expected_note}",
                    expected_impact=0.05,
                    confidence=0.6,
                )
                created += 1

        created += self._evaluate_queue()
        return created

    def _evaluate_queue(self) -> int:
        created = 0
        queue = self.store.list_variant_experiment_queue(limit=300, statuses=["queued", "testing"])
        for entry in queue:
            queue_id, variant_id, target_id, mechanism_id, _channel_id, _planned, _max_trial, _priority, _status, *_ = entry
            variants = self.store.list_offer_variants(target_id=target_id, limit=50)
            incumbents = [v for v in variants if str(v[5]).lower() in {"incumbent", "promoted"}]
            if not incumbents:
                self.store.update_offer_variant_status(variant_id, "incumbent")
                self.store.update_variant_experiment_status(queue_id, "promoted")
                continue
            incumbent_id = int(incumbents[0][0])
            cmp = self.comparator.compare(incumbent_id, int(variant_id), min_trials=3)
            challenger_metrics = self.store.variant_metrics(int(variant_id))
            submissions = int(challenger_metrics[0])
            failure_rate = float(challenger_metrics[5])
            no_response_rate = float(challenger_metrics[6])
            revenue_per_token = float(challenger_metrics[4])

            if cmp.min_trials_guard and submissions < 3:
                self.store.update_variant_experiment_status(queue_id, "testing")
                continue

            if cmp.score_delta > 0.08:
                self.store.update_offer_variant_status(int(variant_id), "promoted")
                self.store.update_offer_variant_status(incumbent_id, "archived")
                self.store.update_variant_experiment_status(queue_id, "promoted")
                self.store.record_creative_recommendation(
                    mechanism_id=int(mechanism_id),
                    target_type=None,
                    variant_id=int(variant_id),
                    blueprint_id=None,
                    asset_id=None,
                    recommendation_type="promote_variant",
                    rationale=f"challenger beat incumbent; {cmp.rationale}",
                    expected_impact=0.15,
                    confidence=0.72,
                )
                self.store.record_creative_recommendation(
                    mechanism_id=int(mechanism_id),
                    target_type=None,
                    variant_id=int(variant_id),
                    blueprint_id=None,
                    asset_id=None,
                    recommendation_type="update_blueprint_default",
                    rationale="winner variant suggests blueprint default update",
                    expected_impact=0.09,
                    confidence=0.67,
                )
                created += 2
                continue

            if failure_rate > 0.5 or no_response_rate > 0.7 or revenue_per_token < 0.02:
                self.store.update_offer_variant_status(int(variant_id), "retired")
                self.store.update_variant_experiment_status(queue_id, "retired")
                self.store.record_creative_recommendation(
                    mechanism_id=int(mechanism_id),
                    target_type=None,
                    variant_id=int(variant_id),
                    blueprint_id=None,
                    asset_id=None,
                    recommendation_type="retire_variant",
                    rationale=f"underperforming challenger; {cmp.rationale}",
                    expected_impact=-0.06,
                    confidence=0.7,
                )
                self.store.record_creative_recommendation(
                    mechanism_id=int(mechanism_id),
                    target_type=None,
                    variant_id=int(variant_id),
                    blueprint_id=None,
                    asset_id=None,
                    recommendation_type="switch_default_execution_mode",
                    rationale="low token efficiency suggests changing default execution mode",
                    expected_impact=0.05,
                    confidence=0.62,
                )
                created += 2
        return created
