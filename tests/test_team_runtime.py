import tempfile
import unittest

from agent.models import AgentState, Opportunity, OpportunityType
from agent.persistence import SQLiteStore
from agent.runtime import AgentRuntime, AgentTeam, MockBroker, MockBrowser, MockShell, RuntimeConfig, SubAgent
from agent.strategy import StrategyEngine


class TeamRuntimeTests(unittest.TestCase):
    def test_team_assignment_and_persistence(self) -> None:
        opportunities = [
            Opportunity("biz", "d", 100, 200, 0.2, OpportunityType.BUSINESS),
            Opportunity("stock", "d", 100, 150, 0.2, OpportunityType.STOCK, symbol="AAPL"),
            Opportunity("crypto", "d", 100, 180, 0.2, OpportunityType.CRYPTO, symbol="BTC-USDT"),
        ]
        state = AgentState(starting_budget=1000, cash=1000)
        team = AgentTeam(
            lead_name="lead",
            members=[
                SubAgent("biz", {OpportunityType.BUSINESS}),
                SubAgent("stock", {OpportunityType.STOCK}),
                SubAgent("crypto", {OpportunityType.CRYPTO}),
            ],
        )

        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            store = SQLiteStore(db_path=tmp.name)
            runtime = AgentRuntime(
                strategy=StrategyEngine(),
                browser=MockBrowser(),
                shell=MockShell(),
                broker=MockBroker(),
                team=team,
                store=store,
                config=RuntimeConfig(max_cycles=5, max_single_trade_ratio=0.5, daily_loss_limit_ratio=0.5),
            )

            result = runtime.run(state, opportunities)
            self.assertEqual(len(result.completed_tasks), 3)

            notes = "\n".join(task.notes for task in result.completed_tasks)
            self.assertIn("assignee=biz", notes)
            self.assertIn("assignee=stock", notes)
            self.assertIn("assignee=crypto", notes)

            kpis = store.team_kpis()
            self.assertEqual(len(kpis), 3)

            pending = store.pending_order_intents()
            self.assertEqual(len(pending), 0)

            events = list(store.recent_events(limit=10))
            self.assertTrue(any(e[1] == "task_done" for e in events))

    def test_risk_guard_blocks_large_trade(self) -> None:
        opportunities = [
            Opportunity("too_big", "d", 400, 500, 0.2, OpportunityType.STOCK, symbol="MSFT"),
        ]
        state = AgentState(starting_budget=500, cash=500)

        runtime = AgentRuntime(
            strategy=StrategyEngine(),
            browser=MockBrowser(),
            shell=MockShell(),
            broker=MockBroker(),
            config=RuntimeConfig(max_cycles=3, max_single_trade_ratio=0.3, daily_loss_limit_ratio=0.5),
        )
        result = runtime.run(state, opportunities)
        self.assertEqual(len(result.completed_tasks), 0)
        self.assertEqual(len(result.failed_tasks), 1)

    def test_recovery_worker_records_pending_intent_events(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            store = SQLiteStore(db_path=tmp.name)
            store.record_order_intent(
                task_id=10,
                market=OpportunityType.CRYPTO,
                symbol="BTC-USDT",
                side="BUY",
                budget=100,
                client_order_id="manual-pending-id",
                status="submitted",
            )
            store.record_order_execution(
                client_order_id="manual-pending-id",
                broker="mock",
                order_id="order-1",
                status="submitted",
                raw_response="{}",
            )

            runtime = AgentRuntime(
                strategy=StrategyEngine(),
                browser=MockBrowser(),
                shell=MockShell(),
                broker=MockBroker(),
                store=store,
            )
            runtime.recover_pending_orders()

            events = list(store.recent_events(limit=10))
            self.assertTrue(any("manual-pending-id" in event[2] for event in events))
            self.assertEqual(len(store.pending_order_intents()), 0)


if __name__ == "__main__":
    unittest.main()
