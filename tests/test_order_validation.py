import json
import tempfile
import unittest

from agent.brokers import BinanceBroker, SymbolRules, UnifiedBroker
from agent.models import AgentState, Opportunity, OpportunityType
from agent.persistence import SQLiteStore
from agent.runtime import AgentRuntime, MockBrowser, MockShell, RuntimeConfig
from agent.strategy import StrategyEngine


class OrderValidationEngineTests(unittest.TestCase):
    def _broker_with_rules(self, rules: SymbolRules, price: float = 100.0) -> BinanceBroker:
        return BinanceBroker(symbol_rules_overrides={"BTCUSDT": rules}, stub_reference_price=price)

    def test_valid_order_passes(self) -> None:
        broker = self._broker_with_rules(SymbolRules(0.01, 0.001, 0.001, 5.0, 2, 3), price=100)
        result = broker.place_order("BTC-USDT", budget=20.0, side="BUY", client_order_id="cid-ok")
        self.assertEqual(result.status, "stub_submitted")
        self.assertTrue(result.validation and result.validation["valid"])

    def test_tick_step_autocorrection(self) -> None:
        broker = self._broker_with_rules(SymbolRules(0.1, 0.05, 0.01, 5.0, 1, 2), price=101.23)
        result = broker.place_order("BTC-USDT", budget=20.0, side="BUY", client_order_id="cid-correct")
        self.assertEqual(result.status, "stub_submitted")
        self.assertTrue(result.validation and result.validation["corrected"])
        self.assertGreaterEqual(len(result.validation["adjustments"]), 1)

    def test_min_qty_failure(self) -> None:
        broker = self._broker_with_rules(SymbolRules(0.01, 0.001, 1.0, 5.0, 2, 3), price=100)
        result = broker.place_order("BTC-USDT", budget=20.0, side="BUY", client_order_id="cid-minqty")
        self.assertEqual(result.status, "rejected_validation")
        self.assertIn("minQty", result.raw)

    def test_min_notional_failure(self) -> None:
        broker = self._broker_with_rules(SymbolRules(0.01, 0.001, 0.001, 50.0, 2, 3), price=100)
        result = broker.place_order("BTC-USDT", budget=20.0, side="BUY", client_order_id="cid-minnotional")
        self.assertEqual(result.status, "rejected_validation")
        self.assertIn("minNotional", result.raw)

    def test_runtime_persists_validation_and_dashboard_visible_raw(self) -> None:
        opportunities = [
            Opportunity("crypto", "d", 20, 30, 0.2, OpportunityType.CRYPTO, symbol="BTC-USDT"),
        ]
        state = AgentState(starting_budget=1000, cash=1000)

        # Force minNotional reject through stub validation
        binance = self._broker_with_rules(SymbolRules(0.01, 0.001, 0.001, 50.0, 2, 3), price=100)
        broker = UnifiedBroker()
        broker.binance = binance

        with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
            store = SQLiteStore(tmp.name)
            runtime = AgentRuntime(
                strategy=StrategyEngine(),
                browser=MockBrowser(),
                shell=MockShell(),
                broker=broker,
                store=store,
                config=RuntimeConfig(max_cycles=3, max_single_trade_ratio=0.8, daily_loss_limit_ratio=0.9),
            )
            result = runtime.run(state, opportunities)
            self.assertEqual(len(result.failed_tasks), 1)

            events = list(store.recent_events(limit=20))
            joined = "\n".join(e[2] for e in events)
            self.assertIn("order_validation_failed", "\n".join(e[1] for e in events))
            self.assertIn("minNotional", joined)

            executions = store.list_order_executions(5)
            self.assertTrue(executions)
            raw = executions[0][5]
            parsed = json.loads(raw)
            self.assertIn("validation", parsed)


if __name__ == "__main__":
    unittest.main()
