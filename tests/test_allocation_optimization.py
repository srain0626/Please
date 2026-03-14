import json
import tempfile
import unittest

from agent import AllocationOptimizer, AllocationScoringEngine
from agent.persistence import SQLiteStore
from dashboard import render_dashboard


class AllocationOptimizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db')
        self.store = SQLiteStore(self.tmp.name)
        self.mechanism_id = self.store.create_income_mechanism(
            mechanism_type='freelancing',
            title='Proposal Engine',
            description='proposal dist',
            expected_revenue=400,
            expected_cost=80,
            expected_token_cost=20,
            automation_potential=0.7,
            repeatability_score=0.75,
            maintenance_cost=20,
            current_stage='scaling',
            status='active',
            confidence_score=0.5,
            time_to_payout=0.5,
        )
        self.target_id = self.store.create_distribution_target(
            mechanism_id=self.mechanism_id,
            target_type='freelance_proposal',
            title='Offer',
            summary='s',
            payload_json='{}',
            status='ready',
        )
        self.channel_id = self.store.create_distribution_channel(
            channel_type='email',
            name='email_opt_stub',
            description='stub',
            config_json='{}',
            is_active=True,
        )
        self.variant_a = self.store.create_offer_variant(
            target_id=self.target_id,
            variant_key='a',
            title='A',
            payload_patch_json=json.dumps({'headline': 'A'}),
            status='active',
        )
        self.variant_b = self.store.create_offer_variant(
            target_id=self.target_id,
            variant_key='b',
            title='B',
            payload_patch_json=json.dumps({'headline': 'B'}),
            status='active',
        )

        # good run for variant A
        run_a = self.store.create_distribution_run(
            target_id=self.target_id,
            channel_id=self.channel_id,
            mechanism_id=self.mechanism_id,
            execution_mode='rule_based',
            status='converted',
            external_ref='ra',
            notes='good',
            variant_id=self.variant_a,
        )
        self.store.record_conversion_event(
            run_id=run_a,
            target_id=self.target_id,
            mechanism_id=self.mechanism_id,
            event_type='sale',
            value_estimate=90.0,
            metadata_json='{}',
        )

        # weak run for variant B
        run_b = self.store.create_distribution_run(
            target_id=self.target_id,
            channel_id=self.channel_id,
            mechanism_id=self.mechanism_id,
            execution_mode='llm_direct',
            status='failed',
            external_ref='rb',
            notes='bad',
            variant_id=self.variant_b,
        )
        self.store.record_conversion_event(
            run_id=run_b,
            target_id=self.target_id,
            mechanism_id=self.mechanism_id,
            event_type='no_response',
            value_estimate=0,
            metadata_json='{}',
        )

    def tearDown(self) -> None:
        self.tmp.close()

    def test_allocation_policy_register_and_list(self) -> None:
        policy_id = self.store.upsert_allocation_policy(
            mechanism_id=self.mechanism_id,
            channel_id=self.channel_id,
            target_type='freelance_proposal',
            execution_mode='rule_based',
            base_weight=1.0,
            min_trials=2,
            max_trials=10,
            cooldown_hours=4.0,
            is_active=True,
        )
        self.assertGreater(policy_id, 0)
        rows = self.store.list_allocation_policies(limit=10)
        self.assertTrue(rows)

    def test_performance_aggregation_and_variant_link(self) -> None:
        by_variant = self.store.performance_summary(dimension='variant', limit=10)
        keys = {row[0] for row in by_variant}
        self.assertIn(str(self.variant_a), keys)
        self.assertIn(str(self.variant_b), keys)

    def test_scoring_engine_returns_breakdown(self) -> None:
        scorer = AllocationScoringEngine(self.store)
        scores = scorer.score_dimension('channel', limit=10)
        self.assertTrue(scores)
        self.assertTrue(hasattr(scores[0], 'score'))
        self.assertTrue(hasattr(scores[0], 'revenue_per_token'))

    def test_recommendation_generation_and_auto_apply(self) -> None:
        self.store.upsert_allocation_policy(
            mechanism_id=self.mechanism_id,
            channel_id=self.channel_id,
            target_type='freelance_proposal',
            execution_mode='rule_based',
            base_weight=1.0,
            min_trials=2,
            max_trials=10,
            cooldown_hours=4.0,
            is_active=True,
        )
        before = float(self.store.list_income_mechanisms(limit=1)[0][12])
        created = AllocationOptimizer(self.store).generate_recommendations()
        self.assertGreater(created, 0)
        recs = self.store.list_allocation_recommendations(limit=20)
        self.assertTrue(any(r[5] in {'promote_variant', 'retire_variant', 'switch_execution_mode', 'increase_allocation', 'decrease_allocation', 'pause_channel'} for r in recs))
        self.assertTrue(any(int(r[10]) in {0, 1} for r in recs))
        after = float(self.store.list_income_mechanisms(limit=1)[0][12])
        self.assertNotEqual(before, after)

    def test_dashboard_contains_allocation_sections(self) -> None:
        AllocationOptimizer(self.store).generate_recommendations()
        html = render_dashboard(self.store)
        self.assertIn('Allocation Policies', html)
        self.assertIn('Offer Variants', html)
        self.assertIn('Reallocation Recommendations', html)
        self.assertIn('Channel Allocation Score Breakdown', html)


if __name__ == '__main__':
    unittest.main()
