from __future__ import annotations

import argparse

from agent import (
    AgentRuntime,
    AllocationOptimizer,
    AgentState,
    AgentTeam,
    AutomationCandidateDetector,
    LLMBrowser,
    LLMShell,
    LLMProvider,
    LabConfig,
    Opportunity,
    OpportunityType,
    RuntimeConfig,
    SQLiteStore,
    StrategyEngine,
    StrategyLab,
    SubAgent,
    UnifiedBroker,
    adapter_for_channel_type,
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
            confidence_score=0.55,
            evidence_score=0.45,
            execution_complexity=0.55,
            repeatability_score=0.65,
            time_to_payout=0.75,
        ),
        Opportunity(
            name="미국 대형주 스윙 전략",
            description="저변동 대형주 분할매수 후 단기 리밸런싱",
            required_budget=150.0,
            expected_return=210.0,
            risk_score=0.35,
            opportunity_type=OpportunityType.STOCK,
            symbol="AAPL",
            confidence_score=0.6,
            evidence_score=0.52,
            execution_complexity=0.4,
            repeatability_score=0.7,
            time_to_payout=0.55,
        ),
        Opportunity(
            name="비트코인 모멘텀 전략",
            description="거래량 증가 구간의 단기 추세 추종",
            required_budget=130.0,
            expected_return=220.0,
            risk_score=0.45,
            opportunity_type=OpportunityType.CRYPTO,
            symbol="BTC-USDT",
            confidence_score=0.58,
            evidence_score=0.5,
            execution_complexity=0.45,
            repeatability_score=0.68,
            time_to_payout=0.45,
        ),
    ]


def seed_income_mechanisms(store: SQLiteStore) -> None:
    if store.list_income_mechanisms(limit=1):
        return

    blogging_id = store.create_income_mechanism(
        mechanism_type="blogging",
        title="AI 자동화 블로그 수익화",
        description="키워드 클러스터링 + 포스트 드래프팅 + 광고/제휴 전환",
        expected_revenue=220.0,
        expected_cost=40.0,
        expected_token_cost=20.0,
        automation_potential=0.85,
        repeatability_score=0.8,
        maintenance_cost=25.0,
        current_stage="mvp",
        status="testing",
        confidence_score=0.62,
        time_to_payout=0.7,
    )
    store.create_process_blueprint(
        mechanism_id=blogging_id,
        task_type="blog_post_drafting",
        title="SEO 포스트 자동 초안",
        description="키워드에서 제목/개요/본문 초안 생성",
        inputs_schema='{"keyword": "str", "intent": "str"}',
        output_schema='{"title": "str", "outline": "list", "draft": "str"}',
        steps_json='["research", "outline", "draft", "qa"]',
        can_be_templated=True,
        can_be_ruled=True,
        can_be_coded=True,
        automation_status="ready",
        estimated_token_cost=3.0,
        estimated_run_cost=0.2,
        reuse_count=0,
    )

    freelancing_id = store.create_income_mechanism(
        mechanism_type="freelancing",
        title="AI 제안서 자동화 외주",
        description="리드 필터링 + 제안서 작성 자동화로 수주율 향상",
        expected_revenue=350.0,
        expected_cost=90.0,
        expected_token_cost=15.0,
        automation_potential=0.6,
        repeatability_score=0.7,
        maintenance_cost=35.0,
        current_stage="scaling",
        status="active",
        confidence_score=0.68,
        time_to_payout=0.45,
    )
    store.create_process_blueprint(
        mechanism_id=freelancing_id,
        task_type="proposal_drafting",
        title="외주 제안서 생성",
        description="요구사항 기반 문제정의/범위/일정/가격 제안",
        inputs_schema='{"client_brief": "str"}',
        output_schema='{"proposal": "str", "price_range": "tuple"}',
        steps_json='["parse_brief", "scope", "pricing", "proposal"]',
        can_be_templated=True,
        can_be_ruled=True,
        can_be_coded=False,
        automation_status="partial",
        estimated_token_cost=2.5,
        estimated_run_cost=0.1,
        reuse_count=0,
    )





def seed_automation_assets(store: SQLiteStore) -> None:
    detector = AutomationCandidateDetector(store)
    detector.detect()
    candidates = store.list_automation_candidates(limit=5)
    if not candidates:
        return
    candidate_id = int(candidates[0][0])
    if not store.list_candidate_assets(candidate_id, limit=1):
        store.record_candidate_asset(
            candidate_id=candidate_id,
            asset_key="prompt:lead-qualifier-v1",
            asset_kind="prompt_template",
            payload='{"goal":"qualify leads quickly","version":"v1"}',
        )
    if not store.list_token_observations(candidate_id, limit=1):
        store.record_token_observation(candidate_id=candidate_id, tokens_in=420, tokens_out=180, cost_usd=0.023)





def seed_distribution_channels(store: SQLiteStore) -> None:
    presets = [
        ("blog", "local_blog_stub", "Local blog publishing stub", '{"base_url":"local://blog"}', True),
        ("email", "email_outreach_stub", "Email/direct outreach stub", '{"provider":"stub"}', True),
        ("marketplace", "marketplace_stub", "Marketplace posting stub", '{"market":"stub"}', True),
    ]
    for channel_type, name, description, config_json, active in presets:
        store.create_distribution_channel(
            channel_type=channel_type,
            name=name,
            description=description,
            config_json=config_json,
            is_active=active,
        )


def seed_distribution_targets(store: SQLiteStore) -> None:
    if store.list_distribution_targets(limit=1):
        return
    mechanisms = store.list_income_mechanisms(limit=10)
    blueprints = store.list_process_blueprints(limit=30)
    blueprint_by_mechanism: dict[int, int] = {}
    for bp in blueprints:
        mechanism_id = int(bp[1])
        if mechanism_id not in blueprint_by_mechanism:
            blueprint_by_mechanism[mechanism_id] = int(bp[0])

    target_by_type = {
        "blogging": "blog_post",
        "freelancing": "freelance_proposal",
        "automation_service": "automation_offer",
        "digital_product": "digital_product_offer",
        "lead_generation": "lead_list",
        "trading": "outreach_message",
    }
    for row in mechanisms:
        mechanism_id = int(row[0])
        mechanism_type = str(row[1])
        title = str(row[2])
        target_type = target_by_type.get(mechanism_type, "outreach_message")
        store.create_distribution_target(
            mechanism_id=mechanism_id,
            blueprint_id=blueprint_by_mechanism.get(mechanism_id),
            asset_id=None,
            target_type=target_type,
            title=f"{title} distribution target",
            summary="stub distributable unit generated by seeder",
            payload_json='{"cta":"book call","tags":["ai","automation"]}',
            status="ready",
        )


def run_distribution_loop(store: SQLiteStore) -> None:
    channels = store.list_distribution_channels(limit=20, active_only=True)
    targets = store.list_distribution_targets(limit=20)
    if not channels or not targets:
        return
    existing_runs = store.list_distribution_runs(limit=200)
    existing_pairs = {(int(r[1]), int(r[2])) for r in existing_runs}
    for target in targets:
        target_id = int(target[0])
        mechanism_id = int(target[1])
        for channel in channels:
            channel_id = int(channel[0])
            channel_type = str(channel[1])
            if (target_id, channel_id) in existing_pairs:
                continue
            variants = store.list_offer_variants(target_id=target_id, limit=2)
            variant_ids = [int(v[0]) for v in variants] or [None]
            adapter = adapter_for_channel_type(channel_type, store)
            for variant_id in variant_ids:
                result = adapter.submit(
                    target_id=target_id,
                    channel_id=channel_id,
                    mechanism_id=mechanism_id,
                    execution_mode="rule_based",
                )
                if variant_id is not None:
                    store.update_distribution_run_variant(result.run_id, variant_id)

def seed_token_policies(store: SQLiteStore) -> None:
    presets = [
        ("business_execution", "automation_service", 240, "code_based", False, "on_failure", "llm_direct", True),
        ("stock_execution", "trading", 180, "rule_based", False, "on_failure", "llm_direct", True),
        ("crypto_execution", "trading", 180, "rule_based", False, "on_failure", "llm_direct", True),
    ]
    for task_type, mechanism_type, budget, preferred, allow_llm, escalation, fallback, caching in presets:
        store.upsert_token_policy(
            task_type=task_type,
            mechanism_type=mechanism_type,
            max_token_budget=budget,
            preferred_execution_mode=preferred,
            allow_llm_direct=allow_llm,
            escalation_condition=escalation,
            fallback_mode=fallback,
            caching_enabled=caching,
        )



def seed_allocation_policies(store: SQLiteStore) -> None:
    if store.list_allocation_policies(limit=1):
        return
    channels = store.list_distribution_channels(limit=50)
    mechanisms = store.list_income_mechanisms(limit=50)
    targets = store.list_distribution_targets(limit=50)

    for mechanism in mechanisms:
        mechanism_id = int(mechanism[0])
        mechanism_type = str(mechanism[1])
        for channel in channels:
            channel_id = int(channel[0])
            store.upsert_allocation_policy(
                mechanism_id=mechanism_id,
                channel_id=channel_id,
                target_type=None,
                execution_mode="rule_based" if mechanism_type != "trading" else "code_based",
                base_weight=1.0,
                min_trials=2,
                max_trials=12,
                cooldown_hours=6.0,
                is_active=True,
            )

    for target in targets:
        target_id = int(target[0])
        target_type = str(target[4])
        store.create_offer_variant(
            target_id=target_id,
            variant_key="headline_a",
            title=f"{target_type} headline A",
            payload_patch_json='{"headline":"A"}',
            status="active",
        )
        store.create_offer_variant(
            target_id=target_id,
            variant_key="headline_b",
            title=f"{target_type} headline B",
            payload_patch_json='{"headline":"B"}',
            status="active",
        )

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
    parser.add_argument(
        "--max-market-exposure-ratio",
        type=float,
        default=0.6,
        help="Max exposure per market (stock/crypto) as ratio of starting budget",
    )
    parser.add_argument(
        "--exploratory-budget-ratio",
        type=float,
        default=0.15,
        help="Budget ratio reserved for hypothesis experiments",
    )
    parser.add_argument("--lab-cycles", type=int, default=2, help="How many strategy-lab research cycles to run")
    parser.add_argument("--db-path", default="agent_state.db", help="SQLite persistence path")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    provider = LLMProvider(args.provider)
    model = args.model or default_model(provider)
    llm = create_llm_client(provider=provider, model=model, live_api=args.live_api)

    state = AgentState(starting_budget=args.budget, cash=args.budget)
    team = build_default_team()
    store = SQLiteStore(db_path=args.db_path)
    seed_income_mechanisms(store)
    seed_automation_assets(store)
    seed_token_policies(store)
    seed_distribution_channels(store)
    seed_distribution_targets(store)
    seed_allocation_policies(store)
    run_distribution_loop(store)
    AllocationOptimizer(store).generate_recommendations()

    lab = StrategyLab(
        store=store,
        config=LabConfig(
            exploratory_budget_ratio=args.exploratory_budget_ratio,
            max_experiments_per_cycle=4,
        ),
    )
    promoted_opportunities: list[Opportunity] = []
    seed = sample_opportunities()
    for _ in range(max(1, args.lab_cycles)):
        promoted_opportunities = lab.research_and_promote(state=state, seed_opportunities=seed)
        seed = promoted_opportunities or seed

    runtime = AgentRuntime(
        strategy=StrategyEngine(),
        browser=LLMBrowser(llm),
        shell=LLMShell(llm),
        broker=UnifiedBroker(),
        team=team,
        store=store,
        config=RuntimeConfig(
            max_cycles=5,
            max_single_trade_ratio=0.35,
            max_market_exposure_ratio=args.max_market_exposure_ratio,
            daily_loss_limit_ratio=0.15,
        ),
    )

    result = runtime.run(state, promoted_opportunities)
    print("=== Autonomous Profit Agent Report ===")
    print(f"provider: {provider.value}")
    print(f"model: {model}")
    print(f"lead_agent: {team.lead_name}")
    print(f"team_size: {len(team.members)}")
    print(f"promoted_opportunities: {len(promoted_opportunities)}")
    print(f"cash: {result.cash:.2f}")
    print(f"revenue: {result.revenue:.2f}")
    print(f"cost: {result.cost:.2f}")
    print(f"profit: {result.profit:.2f}")
    print(f"roi: {result.roi:.2%}")
    print(f"completed_tasks: {len(result.completed_tasks)}")
    print(f"failed_tasks: {len(result.failed_tasks)}")

    print("\n=== Team KPI ===")
    for row in store.team_kpis():
        print(
            f"{row.assignee}: tasks={row.task_count}, revenue={row.revenue:.2f}, "
            f"cost={row.cost:.2f}, profit={row.profit:.2f}"
        )


if __name__ == "__main__":
    main()
