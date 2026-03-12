import tempfile
import unittest

from agent.models import OpportunityType, Task, TaskStatus
from agent.persistence import SQLiteStore
from dashboard import render_dashboard


class DashboardTests(unittest.TestCase):
    def test_render_dashboard_contains_sections(self) -> None:
        with tempfile.NamedTemporaryFile(suffix='.db') as tmp:
            store = SQLiteStore(tmp.name)
            task = Task(
                id=1,
                title='demo',
                action_plan=['a'],
                estimated_cost=100,
                expected_revenue=120,
                channel=OpportunityType.STOCK,
                instrument='AAPL',
                status=TaskStatus.DONE,
                notes='ok',
            )
            store.record_task_run(task=task, assignee='stock-trader', realized_revenue=110)
            store.record_position(
                market=OpportunityType.STOCK,
                symbol='AAPL',
                budget=100,
                side='buy',
                status='open',
                metadata='demo',
            )
            store.record_order_intent(
                task_id=1,
                market=OpportunityType.STOCK,
                symbol='AAPL',
                side='buy',
                budget=100,
                client_order_id='cid-1',
                status='submitted',
            )
            store.record_order_execution(
                client_order_id='cid-1',
                broker='mock',
                order_id='oid-1',
                status='filled',
                raw_response='{}',
            )
            store.snapshot_team_kpis()
            store.record_event('manual_event', 'hello')

            html = render_dashboard(store, flash='ok')
            self.assertIn('Autonomous Profit Agent Dashboard', html)
            self.assertIn('Task Runs', html)
            self.assertIn('Order Intents', html)
            self.assertIn('KPI Snapshots', html)
            self.assertIn('stock-trader', html)

    def test_summary_metrics_and_position_update(self) -> None:
        with tempfile.NamedTemporaryFile(suffix='.db') as tmp:
            store = SQLiteStore(tmp.name)
            store.record_position(
                market=OpportunityType.CRYPTO,
                symbol='BTC-USDT',
                budget=50,
                side='buy',
                status='submitted',
                metadata='x',
            )
            pos_id = store.list_positions(1)[0][0]
            store.update_position_status(pos_id, 'closed')
            self.assertEqual(store.list_positions(1)[0][5], 'closed')
            metrics = store.summary_metrics()
            self.assertEqual(metrics['pending_orders'], 0)


if __name__ == '__main__':
    unittest.main()
