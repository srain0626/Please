import tempfile
import unittest

from agent.execution import ExecutionContext, ExecutionRouter
from agent.persistence import SQLiteStore


class MockBrowser:
    def run(self, instruction: str) -> str:
        return f"b:{instruction}"


class MockShell:
    def run(self, command: str) -> str:
        return f"s:{command}"


class ExecutionRouterTests(unittest.TestCase):
    def test_token_policy_storage_and_preferred_mode(self) -> None:
        with tempfile.NamedTemporaryFile(suffix='.db') as tmp:
            store = SQLiteStore(tmp.name)
            policy_id = store.upsert_token_policy(
                task_type='proposal_drafting',
                mechanism_type='freelancing',
                max_token_budget=250,
                preferred_execution_mode='prompt_template',
                allow_llm_direct=False,
                escalation_condition='on_failure',
                fallback_mode='llm_direct',
                caching_enabled=True,
            )
            self.assertGreater(policy_id, 0)
            resolved = store.resolve_token_policy(task_type='proposal_drafting', mechanism_type='freelancing')
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved[5], 'prompt_template')

    def test_asset_and_blueprint_prefer_cheaper_path(self) -> None:
        with tempfile.NamedTemporaryFile(suffix='.db') as tmp:
            store = SQLiteStore(tmp.name)
            mid = store.create_income_mechanism(
                mechanism_type='automation_service',
                title='ops',
                description='d',
                expected_revenue=200,
                expected_cost=30,
                expected_token_cost=10,
                automation_potential=0.9,
                repeatability_score=0.9,
                maintenance_cost=5,
                current_stage='mvp',
                status='active',
                confidence_score=0.7,
                time_to_payout=0.4,
            )
            store.create_process_blueprint(
                mechanism_id=mid,
                task_type='business_execution',
                title='bp',
                description='d',
                inputs_schema='{}',
                output_schema='{}',
                steps_json='[]',
                can_be_templated=True,
                can_be_ruled=True,
                can_be_coded=True,
                automation_status='ready',
                estimated_token_cost=0.2,
                estimated_run_cost=0.01,
            )
            cid = store.upsert_automation_candidate(
                mechanism_id=mid,
                candidate_type='workflow_automation',
                title='cand',
                status='active',
                confidence_score=0.8,
                reason='r',
            )
            store.record_candidate_asset(candidate_id=cid, asset_key='script:runner', asset_kind='script', payload='{}')
            store.upsert_token_policy(
                task_type='business_execution',
                mechanism_type='automation_service',
                max_token_budget=200,
                preferred_execution_mode='code_based',
                allow_llm_direct=False,
                escalation_condition='on_failure',
                fallback_mode='llm_direct',
                caching_enabled=True,
            )

            router = ExecutionRouter(store=store, browser_tool=MockBrowser(), shell_tool=MockShell())
            ctx = ExecutionContext(
                task_id=1,
                task_type='business_execution',
                mechanism_type='automation_service',
                mechanism_id=None,
                instruction='repeatable work',
                expected_value=90,
                confidence=0.7,
            )
            result = router.execute(ctx)
            self.assertEqual(result.mode, 'code_based')
            self.assertGreaterEqual(result.estimated_token_savings, 1000)

            # same input should hit cache and keep low-cost path
            cached = router.execute(ctx)
            self.assertTrue(cached.cache_hit)
            self.assertEqual(cached.estimated_token_cost, 0)

    def test_fallback_and_escalation(self) -> None:
        with tempfile.NamedTemporaryFile(suffix='.db') as tmp:
            store = SQLiteStore(tmp.name)
            store.upsert_token_policy(
                task_type='stock_execution',
                mechanism_type='trading',
                max_token_budget=180,
                preferred_execution_mode='rule_based',
                allow_llm_direct=True,
                escalation_condition='on_failure',
                fallback_mode='llm_direct',
                caching_enabled=False,
            )
            router = ExecutionRouter(store=store, browser_tool=MockBrowser(), shell_tool=MockShell())
            router.executors['rule_based'] = type('FailRule', (), {'run': lambda self, _: (_ for _ in ()).throw(RuntimeError('rule fail'))})()
            ctx = ExecutionContext(
                task_id=2,
                task_type='stock_execution',
                mechanism_type='trading',
                mechanism_id=None,
                instruction='volatile stock task',
                expected_value=20,
                confidence=0.4,
            )
            result = router.execute(ctx)
            self.assertEqual(result.mode, 'llm_direct')
            self.assertTrue(result.escalated)

            summary = store.execution_savings_summary()
            self.assertIn('replaced_llm_count', summary)
            usage = dict(store.execution_mode_usage())
            self.assertGreaterEqual(usage.get('llm_direct', 0), 1)

    def test_execution_api_data_shapes(self) -> None:
        with tempfile.NamedTemporaryFile(suffix='.db') as tmp:
            store = SQLiteStore(tmp.name)
            store.upsert_token_policy(
                task_type='crypto_execution',
                mechanism_type='trading',
                max_token_budget=180,
                preferred_execution_mode='rule_based',
                allow_llm_direct=False,
                escalation_condition='on_failure',
                fallback_mode='llm_direct',
                caching_enabled=True,
            )
            router = ExecutionRouter(store=store, browser_tool=MockBrowser(), shell_tool=MockShell())
            result = router.execute(
                ExecutionContext(
                    task_id=3,
                    task_type='crypto_execution',
                    mechanism_type='trading',
                    mechanism_id=None,
                    instruction='btc rebalance',
                    expected_value=40,
                    confidence=0.5,
                )
            )
            self.assertEqual(result.mode, 'rule_based')
            self.assertTrue(store.list_token_policies())
            self.assertTrue(store.recent_execution_routes())
            metrics = store.summary_metrics()
            self.assertIn('estimated_token_savings', metrics)


if __name__ == '__main__':
    unittest.main()
