import json
import tempfile
import unittest

from agent import OfferSelfImprovementLoop, VariantGenerator, VariantPerformanceComparator
from agent.persistence import SQLiteStore
from dashboard import render_dashboard


class SelfImprovementLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix='.db')
        self.store = SQLiteStore(self.tmp.name)
        self.mechanism_id = self.store.create_income_mechanism(
            mechanism_type='automation_service',
            title='Automation Offer',
            description='desc',
            expected_revenue=300,
            expected_cost=70,
            expected_token_cost=30,
            automation_potential=0.8,
            repeatability_score=0.7,
            maintenance_cost=25,
            current_stage='mvp',
            status='active',
            confidence_score=0.7,
            time_to_payout=0.5,
        )
        self.target_id = self.store.create_distribution_target(
            mechanism_id=self.mechanism_id,
            target_type='automation_offer',
            title='Automation offer target',
            summary='s',
            payload_json='{}',
            status='ready',
        )
        self.channel_id = self.store.create_distribution_channel(
            channel_type='email',
            name='si_email',
            description='d',
            config_json='{}',
            is_active=True,
        )
        self.base_variant = self.store.create_offer_variant(
            target_id=self.target_id,
            variant_key='incumbent_base',
            title='Base',
            payload_patch_json='{}',
            status='incumbent',
        )

    def tearDown(self) -> None:
        self.tmp.close()

    def _seed_variant_metrics(self, variant_id: int, status: str, event_type: str, value: float, execution_mode: str = 'rule_based') -> None:
        run_id = self.store.create_distribution_run(
            target_id=self.target_id,
            channel_id=self.channel_id,
            mechanism_id=self.mechanism_id,
            execution_mode=execution_mode,
            status=status,
            external_ref=f'ref-{variant_id}-{event_type}',
            notes='n',
            variant_id=variant_id,
        )
        self.store.record_conversion_event(
            run_id=run_id,
            target_id=self.target_id,
            mechanism_id=self.mechanism_id,
            event_type=event_type,
            value_estimate=value,
            metadata_json='{}',
        )

    def test_variant_generator_creates_candidates(self) -> None:
        generated = VariantGenerator(self.store).generate_for_target(self.target_id, limit=3)
        self.assertEqual(len(generated), 3)
        self.assertTrue(all(g.variant_key.startswith('gen_') for g in generated))

    def test_experiment_queue_register_and_list(self) -> None:
        variant_id = self.store.create_offer_variant(
            target_id=self.target_id,
            variant_key='queue_test',
            title='Q',
            payload_patch_json='{}',
            status='proposed',
        )
        qid = self.store.enqueue_variant_experiment(
            variant_id=variant_id,
            target_id=self.target_id,
            mechanism_id=self.mechanism_id,
            channel_id=self.channel_id,
            planned_trial_count=2,
            max_trial_count=4,
            priority=0.5,
            status='queued',
        )
        self.assertGreater(qid, 0)
        rows = self.store.list_variant_experiment_queue(limit=10)
        self.assertTrue(rows)

    def test_comparator_small_sample_guard(self) -> None:
        challenger = self.store.create_offer_variant(
            target_id=self.target_id,
            variant_key='challenger_small',
            title='C',
            payload_patch_json='{}',
            status='testing',
        )
        self._seed_variant_metrics(self.base_variant, 'converted', 'sale', 40)
        self._seed_variant_metrics(challenger, 'converted', 'sale', 50)
        cmp = VariantPerformanceComparator(self.store).compare(self.base_variant, challenger, min_trials=3)
        self.assertTrue(cmp.min_trials_guard)
        self.assertGreater(cmp.small_sample_penalty, 0)

    def test_promotion_and_retirement_rules(self) -> None:
        # base has mediocre performance
        for _ in range(4):
            self._seed_variant_metrics(self.base_variant, 'responded', 'reply', 0)

        challenger_good = self.store.create_offer_variant(
            target_id=self.target_id,
            variant_key='challenger_good',
            title='Good',
            payload_patch_json='{}',
            status='testing',
        )
        for _ in range(4):
            self._seed_variant_metrics(challenger_good, 'converted', 'sale', 80)

        challenger_bad = self.store.create_offer_variant(
            target_id=self.target_id,
            variant_key='challenger_bad',
            title='Bad',
            payload_patch_json='{}',
            status='testing',
        )
        for _ in range(4):
            self._seed_variant_metrics(challenger_bad, 'failed', 'no_response', 0, execution_mode='llm_direct')

        self.store.enqueue_variant_experiment(
            variant_id=challenger_good,
            target_id=self.target_id,
            mechanism_id=self.mechanism_id,
            channel_id=self.channel_id,
            planned_trial_count=2,
            max_trial_count=5,
            priority=0.8,
            status='testing',
        )
        self.store.enqueue_variant_experiment(
            variant_id=challenger_bad,
            target_id=self.target_id,
            mechanism_id=self.mechanism_id,
            channel_id=self.channel_id,
            planned_trial_count=2,
            max_trial_count=5,
            priority=0.2,
            status='testing',
        )

        created = OfferSelfImprovementLoop(self.store).run(max_new_variants_per_target=0)
        self.assertGreaterEqual(created, 2)

        variants = {v[2]: v[5] for v in self.store.list_offer_variants(target_id=self.target_id, limit=20)}
        self.assertIn(variants.get('challenger_good'), {'promoted', 'incumbent'})
        self.assertEqual(variants.get('challenger_bad'), 'retired')

    def test_creative_recommendations_and_blocked_generation(self) -> None:
        # push mechanism confidence down to trigger block
        self.store.apply_distribution_feedback(self.mechanism_id, confidence_delta=-0.5, repeatability_delta=0)
        created = OfferSelfImprovementLoop(self.store).run(max_new_variants_per_target=1, min_mechanism_confidence=0.5)
        self.assertGreaterEqual(created, 0)
        recs = self.store.list_creative_recommendations(limit=20)
        self.assertTrue(any(r[10] == 'blocked' for r in recs))

    def test_dashboard_reflects_self_improvement_sections(self) -> None:
        OfferSelfImprovementLoop(self.store).run(max_new_variants_per_target=1)
        html = render_dashboard(self.store)
        self.assertIn('Variant Experiment Queue', html)
        self.assertIn('Base vs Challenger Comparisons', html)
        self.assertIn('Creative Improvement Recommendations', html)


if __name__ == '__main__':
    unittest.main()
