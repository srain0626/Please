import tempfile
import unittest

from agent.mechanisms import SurvivalScorer
from agent.persistence import SQLiteStore
from agent.strategy import StrategyEngine


class MechanismRegistryTests(unittest.TestCase):
    def test_mechanism_register_and_list(self) -> None:
        with tempfile.NamedTemporaryFile(suffix='.db') as tmp:
            store = SQLiteStore(tmp.name)
            mid = store.create_income_mechanism(
                mechanism_type='blogging',
                title='blog',
                description='desc',
                expected_revenue=100,
                expected_cost=20,
                expected_token_cost=10,
                automation_potential=0.8,
                repeatability_score=0.7,
                maintenance_cost=10,
                current_stage='mvp',
                status='testing',
                confidence_score=0.6,
                time_to_payout=0.7,
            )
            rows = store.list_income_mechanisms()
            self.assertEqual(rows[0][0], mid)
            self.assertEqual(rows[0][1], 'blogging')

    def test_blueprint_create_and_list(self) -> None:
        with tempfile.NamedTemporaryFile(suffix='.db') as tmp:
            store = SQLiteStore(tmp.name)
            mid = store.create_income_mechanism(
                mechanism_type='freelancing',
                title='free',
                description='desc',
                expected_revenue=200,
                expected_cost=80,
                expected_token_cost=10,
                automation_potential=0.5,
                repeatability_score=0.6,
                maintenance_cost=20,
                current_stage='mvp',
                status='active',
                confidence_score=0.55,
                time_to_payout=0.5,
            )
            bid = store.create_process_blueprint(
                mechanism_id=mid,
                task_type='proposal_drafting',
                title='proposal',
                description='d',
                inputs_schema='{}',
                output_schema='{}',
                steps_json='[]',
                can_be_templated=True,
                can_be_ruled=True,
                can_be_coded=False,
                automation_status='partial',
                estimated_token_cost=1.0,
                estimated_run_cost=0.1,
                reuse_count=0,
            )
            rows = store.list_process_blueprints()
            self.assertEqual(rows[0][0], bid)
            self.assertEqual(rows[0][1], mid)

    def test_survival_score_and_strategy_wrapper(self) -> None:
        raw = SurvivalScorer.score(
            expected_revenue=300,
            expected_cost=100,
            expected_token_cost=20,
            automation_potential=0.9,
            repeatability_score=0.8,
            maintenance_cost=30,
            confidence_score=0.7,
            time_to_payout=0.4,
        )
        self.assertGreater(raw.final_score, 0)
        engine = StrategyEngine()
        wrapped = engine.score_mechanism(
            expected_revenue=300,
            expected_cost=100,
            expected_token_cost=20,
            automation_potential=0.9,
            repeatability_score=0.8,
            maintenance_cost=30,
            confidence_score=0.7,
            time_to_payout=0.4,
        )
        self.assertIn('final_score', wrapped)
        self.assertIn('net_value_estimate', wrapped)

    def test_dashboard_api_related_store_data(self) -> None:
        with tempfile.NamedTemporaryFile(suffix='.db') as tmp:
            store = SQLiteStore(tmp.name)
            mid = store.create_income_mechanism(
                mechanism_type='digital_product',
                title='template pack',
                description='desc',
                expected_revenue=120,
                expected_cost=15,
                expected_token_cost=5,
                automation_potential=0.9,
                repeatability_score=0.95,
                maintenance_cost=8,
                current_stage='mvp',
                status='active',
                confidence_score=0.7,
                time_to_payout=0.6,
            )
            store.create_process_blueprint(
                mechanism_id=mid,
                task_type='opportunity_scoring',
                title='score',
                description='d',
                inputs_schema='{}',
                output_schema='{}',
                steps_json='[]',
                can_be_templated=True,
                can_be_ruled=True,
                can_be_coded=True,
                automation_status='ready',
                estimated_token_cost=0.5,
                estimated_run_cost=0.01,
                reuse_count=3,
            )
            metrics = store.summary_metrics()
            self.assertEqual(metrics['mechanism_count'], 1)
            self.assertEqual(metrics['blueprint_count'], 1)
            self.assertTrue(store.mechanism_status_counts())


if __name__ == '__main__':
    unittest.main()
