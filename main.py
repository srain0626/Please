from __future__ import annotations

import argparse

from agent import (
    AgentRuntime,
    AgentState,
    AgentTeam,
    LLMBrowser,
    LLMShell,
    LLMProvider,
    MockBroker,
    Opportunity,
    OpportunityType,
    StrategyEngine,
    SubAgent,
    create_llm_client,
    default_model,
)


def sample_opportunities() -> list[Opportunity]:
    return [
        Opportunity(
            name="B2B 리드 생성 마이크로서비스",
            description="니치 산업 대상 리드 수집 + 이메일 퍼널",
            required_budget=250.0,
            expected_return=500.0,
            risk_score=0.3,
            opportunity_type=OpportunityType.BUSINESS,
        ),
        Opportunity(
            name="미국 대형주 스윙 전략",
            description="저변동 대형주 분할매수 후 단기 리밸런싱",
            required_budget=150.0,
            expected_return=210.0,
            risk_score=0.35,
            opportunity_type=OpportunityType.STOCK,
            symbol="AAPL",
        ),
        Opportunity(
            name="비트코인 모멘텀 전략",
            description="거래량 증가 구간의 단기 추세 추종",
            required_budget=130.0,
            expected_return=220.0,
            risk_score=0.45,
            opportunity_type=OpportunityType.CRYPTO,
            symbol="BTC-USD",
        ),
    ]


def build_default_team() -> AgentTeam:
    return AgentTeam(
        lead_name="main-agent",
        members=[
            SubAgent(name="biz-operator", specialties={OpportunityType.BUSINESS}),
            SubAgent(name="stock-trader", specialties={OpportunityType.STOCK}),
            SubAgent(name="crypto-trader", specialties={OpportunityType.CRYPTO}),
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Autonomous Profit Agent")
    parser.add_argument(
        "--provider",
        choices=[p.value for p in LLMProvider],
        default="openai",
        help="LLM provider: openai | claude | copilot",
    )
    parser.add_argument("--model", default=None, help="Override model name")
    parser.add_argument(
        "--live-api",
        action="store_true",
        help="Call live API if provider API key exists. Default is dry-run stub.",
    )
    parser.add_argument("--budget", type=float, default=700.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    provider = LLMProvider(args.provider)
    model = args.model or default_model(provider)
    llm = create_llm_client(provider=provider, model=model, live_api=args.live_api)

    state = AgentState(starting_budget=args.budget, cash=args.budget)
    team = build_default_team()
    runtime = AgentRuntime(
        strategy=StrategyEngine(),
        browser=LLMBrowser(llm),
        shell=LLMShell(llm),
        broker=MockBroker(),
        team=team,
    )

    result = runtime.run(state, sample_opportunities())
    print("=== Autonomous Profit Agent Report ===")
    print(f"provider: {provider.value}")
    print(f"model: {model}")
    print(f"lead_agent: {team.lead_name}")
    print(f"team_size: {len(team.members)}")
    print(f"cash: {result.cash:.2f}")
    print(f"revenue: {result.revenue:.2f}")
    print(f"cost: {result.cost:.2f}")
    print(f"profit: {result.profit:.2f}")
    print(f"roi: {result.roi:.2%}")
    print(f"completed_tasks: {len(result.completed_tasks)}")
    print(f"failed_tasks: {len(result.failed_tasks)}")


if __name__ == "__main__":
    main()
