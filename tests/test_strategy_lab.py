import tempfile
import unittest

from agent.lab import LabConfig, OpportunityFactory, StrategyLab
from agent.models import AgentState, Opportunity, OpportunityType
from agent.persistence import SQLiteStore
from agent.strategy import StrategyEngine


class StrategyLabTests(unittest.TestCase):
    def test_opportunity_factory_generates_opportunities(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            store = SQLiteStore(tmp.name)
            store.record_event("task_done", "seed")
            factory = OpportunityFactory(store)
            generated = factory.generate([])
            self.assertGreaterEqual(len(generated), 1)

    def test_hypothesis_created_and_persisted(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            store = SQLiteStore(tmp.name)
            lab = StrategyLab(store, LabConfig(max_experiments_per_cycle=1))
            state = AgentState(starting_budget=500, cash=500)
            lab.research_and_promote(
                state,
                [
                    Opportunity(
                        "test",
                        "thesis",
                        50,
                        70,
                        0.2,
                        OpportunityType.CRYPTO,
                        "BTC-USDT",
                        0.55,
                        0.6,
                        0.3,
                        0.7,
                        0.4,
                    )
                ],
            )
            hypotheses = store.list_hypotheses(limit=10)
            self.assertGreaterEqual(len(hypotheses), 1)

    def test_experiment_updates_confidence_and_rejects_low_confidence(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            store = SQLiteStore(tmp.name)
            lab = StrategyLab(
                store,
                LabConfig(
                    max_experiments_per_cycle=10,
                    confidence_decrease_fail=0.4,
                    rejected_threshold=0.3,
                ),
            )
            state = AgentState(starting_budget=500, cash=500)

            seed = Opportunity(
                "weak-edge",
                "bad thesis",
                80,
                70,
                0.9,
                OpportunityType.CRYPTO,
                "BTC-USDT",
                0.35,
                0.2,
                0.9,
                0.2,
                0.9,
            )
            lab.research_and_promote(state, [seed])
            hypotheses = store.list_hypotheses(limit=20)
            weak_hypo = next(h for h in hypotheses if h[1] == "weak-edge")
            self.assertLessEqual(float(weak_hypo[5]), 0.35)
            self.assertEqual(weak_hypo[7], "rejected")

    def test_validated_strategy_only_promoted(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            store = SQLiteStore(tmp.name)
            lab = StrategyLab(
                store,
                LabConfig(
                    max_experiments_per_cycle=2,
                    confidence_increase_success=0.3,
                    validated_threshold=0.7,
                    min_experiments_for_validation=1,
                    fallback_promote_top_testing=False,
                ),
            )
            state = AgentState(starting_budget=1000, cash=1000)

            strong = Opportunity(
                "strong-edge",
                "good thesis",
                60,
                120,
                0.2,
                OpportunityType.STOCK,
                "AAPL",
                0.65,
                0.8,
                0.2,
                0.8,
                0.4,
            )
            weak = Opportunity(
                "weak-edge",
                "weak thesis",
                60,
                61,
                0.7,
                OpportunityType.STOCK,
                "MSFT",
                0.4,
                0.3,
                0.8,
                0.2,
                0.8,
            )
            promoted = lab.research_and_promote(state, [strong, weak])
            promoted_names = {p.name for p in promoted}
            self.assertIn("strong-edge", promoted_names)
            self.assertNotIn("weak-edge", promoted_names)

    def test_multifactor_scoring_uses_confidence_and_evidence(self) -> None:
        engine = StrategyEngine()
        high = Opportunity(
            "high",
            "d",
            100,
            140,
            0.3,
            OpportunityType.BUSINESS,
            "",
            0.9,
            0.9,
            0.2,
            0.8,
            0.3,
        )
        low = Opportunity(
            "low",
            "d",
            100,
            140,
            0.3,
            OpportunityType.BUSINESS,
            "",
            0.2,
            0.2,
            0.8,
            0.2,
            0.9,
        )
        self.assertGreater(engine.score(high), engine.score(low))

    def test_dashboard_api_reflects_hypothesis_and_experiment(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            store = SQLiteStore(tmp.name)
            hid = store.upsert_hypothesis(
                title="h1",
                thesis="t",
                evidence="e",
                expected_edge=0.2,
                confidence_score=0.7,
                invalidation_rule="rule",
                status="validated",
                linked_opportunity_key="k1",
            )
            store.record_experiment_run(
                hypothesis_id=hid,
                allocated_budget=20,
                result_pnl=4,
                result_return_pct=0.2,
                outcome="success",
                failure_reason="",
                notes="ok",
            )
            self.assertTrue(store.hypothesis_status_counts())
            self.assertTrue(store.recent_experiment_runs())
            summary = store.lab_summary()
            self.assertEqual(summary["experiment_count"], 1)

    def test_fallback_promotion_when_no_validated(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            store = SQLiteStore(tmp.name)
            lab = StrategyLab(
                store,
                LabConfig(
                    max_experiments_per_cycle=1,
                    validated_threshold=0.95,
                    min_experiments_for_validation=5,
                    fallback_promote_top_testing=True,
                    fallback_max_promotions=1,
                ),
            )
            state = AgentState(starting_budget=300, cash=300)
            seed = Opportunity(
                "mid-edge",
                "thesis",
                50,
                70,
                0.3,
                OpportunityType.CRYPTO,
                "BTC-USDT",
                0.55,
                0.6,
                0.4,
                0.6,
                0.4,
            )
            promoted = lab.research_and_promote(state, [seed])
            self.assertEqual(len(promoted), 1)


if __name__ == "__main__":
    unittest.main()
