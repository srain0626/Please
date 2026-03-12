import unittest

from agent.models import AgentState, Opportunity, OpportunityType
from agent.runtime import AgentRuntime, AgentTeam, MockBroker, MockBrowser, MockShell, SubAgent
from agent.strategy import StrategyEngine


class TeamRuntimeTests(unittest.TestCase):
    def test_team_assignment_by_market(self) -> None:
        opportunities = [
            Opportunity("biz", "d", 100, 200, 0.2, OpportunityType.BUSINESS),
            Opportunity("stock", "d", 100, 150, 0.2, OpportunityType.STOCK, symbol="AAPL"),
            Opportunity("crypto", "d", 100, 180, 0.2, OpportunityType.CRYPTO, symbol="BTC-USD"),
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
        runtime = AgentRuntime(
            strategy=StrategyEngine(),
            browser=MockBrowser(),
            shell=MockShell(),
            broker=MockBroker(),
            team=team,
        )

        result = runtime.run(state, opportunities)
        self.assertEqual(len(result.completed_tasks), 3)

        notes = "\n".join(task.notes for task in result.completed_tasks)
        self.assertIn("assignee=biz", notes)
        self.assertIn("assignee=stock", notes)
        self.assertIn("assignee=crypto", notes)


if __name__ == "__main__":
    unittest.main()
