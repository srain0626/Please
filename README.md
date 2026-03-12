# Autonomous Profit Agent (PoC)

브라우저 + 명령어 실행환경을 가진 AI 에이전트가 **예산 기반으로 수익 기회를 선택하고, 다음 액션을 자율적으로 실행**하는 프로젝트의 실행형 PoC입니다.

Conway Research Automaton 스타일(계획 → 실행 → 평가 → 재계획) 루프를 반영했고, LLM 공급자로 **OpenAI / Claude / Copilot**을 선택할 수 있습니다.

## 이번 개선 사항

- **주식 투자 기능**: `OpportunityType.STOCK` + 브로커 주문 경로
- **가상화폐 투자 기능**: `OpportunityType.CRYPTO` + 브로커 주문 경로
- **에이전트 팀 기능**: 메인 에이전트가 서브 에이전트 팀을 구성해 시장별로 업무를 분담

## 핵심 개념

- **Budget-aware planning**: 보유 현금과 안전 예산(reserve)을 고려해 실행할 기회만 선택
- **Risk policy**: 리스크 점수가 높은 기회는 자동 제외
- **Autonomous loop**: 전략 엔진이 Task를 만들고 런타임이 브라우저/셸/브로커 도구를 통해 실행
- **Provider-pluggable LLM**: openai / claude / copilot 중 선택
- **Team orchestration**: `main-agent`가 `biz-operator`, `stock-trader`, `crypto-trader`에게 태스크를 배정

## 프로젝트 구조

```text
.
├── agent
│   ├── __init__.py
│   ├── llm.py         # LLM provider 어댑터(OpenAI/Claude/Copilot)
│   ├── models.py      # 상태/기회/태스크 데이터 모델(+시장 타입)
│   ├── strategy.py    # 리스크/예산 기반 기회 선택 + 시장별 플랜
│   └── runtime.py     # 실행 루프 + 팀 오케스트레이션 + 브로커
├── tests
│   └── test_team_runtime.py
├── main.py            # CLI 엔트리포인트
└── README.md
```

## 빠른 실행 (기본: Dry-run)

```bash
python main.py --provider openai
python main.py --provider claude
python main.py --provider copilot
```

- 기본은 **dry-run(stub)** 이므로 API 키 없이도 동작합니다.
- `--live-api`를 붙이면 실제 API를 호출합니다(해당 키 필요).

## 실 API 사용

### 1) OpenAI

```bash
export OPENAI_API_KEY="..."
python main.py --provider openai --model gpt-4o-mini --live-api
```

### 2) Claude (Anthropic)

```bash
export ANTHROPIC_API_KEY="..."
python main.py --provider claude --model claude-3-5-sonnet-latest --live-api
```

### 3) Copilot (GitHub Models)

```bash
export GITHUB_TOKEN="..."
python main.py --provider copilot --model gpt-4o-mini --live-api
```

## CLI 옵션

- `--provider`: `openai | claude | copilot`
- `--model`: 모델명 오버라이드
- `--live-api`: 실제 API 호출 활성화 (기본 off)
- `--budget`: 시작 예산(기본 700)

## 구현 포인트

1. `StrategyEngine`
   - 기대수익-비용 중심 정렬
   - `max_risk_score` 초과 기회 제외
   - `reserve_ratio` 안전자금 보존
   - 시장 타입(사업/주식/가상화폐)에 따라 액션 플랜 분기

2. `AgentRuntime`
   - 메인 에이전트가 팀(`AgentTeam`)을 통해 서브 에이전트에 태스크 배정
   - `BrokerTool`로 주식/가상화폐 주문 실행 경로 처리
   - 시장별 보수적 실현계수로 비용/매출 반영

3. `LLM provider layer`
   - `agent/llm.py`에서 provider별 endpoint/header/payload 처리
   - 키가 없거나 `--live-api` 미사용이면 자동으로 stub 모드

## 테스트

```bash
python -m unittest -v
```

## 다음 단계

- 실제 증권/거래소 API 연동 (한국/미국 증권사, Binance/Upbit 등)
- 주문 안전장치(최대 슬리피지, 최대 손실률, 서킷브레이커)
- 포지션/체결/손익 영속화 DB 추가
- 팀 단위 KPI(에이전트별 승률/손익) 대시보드
