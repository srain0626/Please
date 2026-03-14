import tempfile
import unittest

from agent.automation import AutomationCandidateDetector, apply_candidate_transition
from agent.persistence import SQLiteStore
from dashboard import render_dashboard


class AutomationTests(unittest.TestCase):
    def test_detector_candidate_type_and_status_transition(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            store = SQLiteStore(tmp.name)
            mechanism_id = store.create_income_mechanism(
                mechanism_type="automation_service",
                title="Ops Automation",
                description="service",
                expected_revenue=200,
                expected_cost=40,
                expected_token_cost=10,
                automation_potential=0.9,
                repeatability_score=0.85,
                maintenance_cost=15,
                current_stage="mvp",
                status="testing",
                confidence_score=0.6,
                time_to_payout=0.5,
            )
            detector = AutomationCandidateDetector(store)
            detector.detect()
            candidates = store.list_automation_candidates()
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0][2], "productized_automation")

            transition = apply_candidate_transition(candidates[0][4], "approve")
            self.assertTrue(store.update_automation_candidate_status(candidates[0][0], transition.target))
            self.assertEqual(store.list_automation_candidates()[0][4], "evaluating")

            with self.assertRaises(ValueError):
                store.update_automation_candidate_status(candidates[0][0], "BAD")

            self.assertEqual(mechanism_id, candidates[0][1])

    def test_token_observation_saved_and_dashboard_reflects(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            store = SQLiteStore(tmp.name)
            mechanism_id = store.create_income_mechanism(
                mechanism_type="blogging",
                title="Blog Auto",
                description="x",
                expected_revenue=100,
                expected_cost=20,
                expected_token_cost=5,
                automation_potential=0.8,
                repeatability_score=0.75,
                maintenance_cost=8,
                current_stage="mvp",
                status="active",
                confidence_score=0.6,
                time_to_payout=0.6,
            )
            candidate_id = store.upsert_automation_candidate(
                mechanism_id=mechanism_id,
                candidate_type="workflow_automation",
                title="candidate",
                status="proposed",
                confidence_score=0.72,
                reason="seed",
            )
            store.record_candidate_asset(
                candidate_id=candidate_id,
                asset_key="script:post-drafter",
                asset_kind="script",
                payload='{"lang":"py"}',
            )
            store.record_token_observation(candidate_id=candidate_id, tokens_in=1000, tokens_out=250, cost_usd=0.11)

            token_summary = store.token_observation_summary()
            self.assertEqual(token_summary["observation_count"], 1)
            self.assertEqual(token_summary["tokens_in"], 1000)

            html = render_dashboard(store)
            self.assertIn("Automation Candidates", html)
            self.assertIn("Token Cost (USD)", html)


if __name__ == "__main__":
    unittest.main()
