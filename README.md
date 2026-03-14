# Autonomous Profit Agent (PoC)

브라우저 + 명령어 실행환경을 가진 AI 에이전트가 **예산 기반으로 수익 기회를 선택하고, 다음 액션을 자율적으로 실행**하는 프로젝트의 실행형 PoC입니다.

Conway Research Automaton 스타일(계획 → 실행 → 평가 → 재계획) 루프를 반영했고, LLM 공급자로 **OpenAI / Claude / Copilot**을 선택할 수 있습니다.

이번 버전은 단순 주문 실행을 넘어 **기회 생성 → 가설화 → 소액 실험 → confidence 업데이트 → validated 전략 승격**의 Strategy Lab 루프를 포함합니다.

## 이번 단계에서 추가된 핵심 기능

- **메인 에이전트 + 서브 에이전트 팀 오케스트레이션**
- **메리츠증권 / Binance 브로커 어댑터 연결 계층** (`UnifiedBroker`)
- **주문 안정성 강화**
  - Binance signed endpoint(HMAC SHA-256) + `timestamp`/`recvWindow`
  - 메리츠 요청용 HMAC 기반 서명 헤더 스캐폴딩
  - `client_order_id`(멱등키) 기반 주문 추적
  - 주문 조회(`get_order`) / 취소(`cancel_order`) API 진입점
  - 재시도(백오프) HTTP 호출
  - **Order Validation Engine (Binance)**: tick size / step size / minQty / minNotional / precision 사전검증 및 자동 보정
- **SQLite 영속성 확장**
  - 기존: `task_runs`, `positions`, `system_events`
  - 추가: `order_intents`, `order_executions`, `team_kpi_snapshots`
- **Opportunity Factory**: market signal + recurring internal pattern 기반 기회 생성
- **Hypothesis / Experiment Persistence**: `hypotheses`, `experiment_runs` 추가
- **Strategy Lab Loop**: 실험 결과에 따라 confidence 증감 및 상태 전환('proposed/testing/validated/rejected/archived')
- **Adaptive Learning Upgrade**: 실험 이력(win-rate/평균수익률) 기반 confidence 보정, fallback promotion, rejected 자동 아카이빙
- **Income Mechanism Registry**: trading/blogging/freelancing/automation_service/digital_product/lead_generation 공통 모델
- **Process Blueprint Registry**: 메커니즘별 반복 작업 설계도(JSON schema + steps)
- **Automation Candidate Detector**: income mechanism에서 자동화 후보 추출 + 상태 전이
- **Automation Asset/Token Tracking**: 후보별 asset(prompt/script) 및 token cost 관측치 저장
- **Token Economy Policy**: task_type/mechanism 기준 max token budget + preferred mode + fallback/escalation 정책
- **Execution Router**: cheap-first/deterministic-first/reusable-first 기반 `llm_direct|prompt_template|rule_based|code_based` 실행 경로 선택
- **Execution Cache/Reuse Hook**: 동일 입력 반복시 캐시 재사용으로 토큰 비용 절감
- **리커버리 워커 스캐폴딩**
  - 런타임 시작 시 미완료 주문 의도(`order_intents`)를 스캔해 이벤트로 기록
- **리스크 가드레일**: 단일 트레이드 비중 제한, 시장별 익스포저 한도, 손실 한도 초과 시 실행 중단

## 프로젝트 구조

```text
.
├── agent
│   ├── __init__.py
│   ├── brokers.py      # Meritz/Binance/Unified broker adapters (+signed requests)
│   ├── lab.py          # opportunity factory + hypothesis/experiment loop
│   ├── llm.py          # LLM provider adapters
│   ├── models.py       # domain models
│   ├── persistence.py  # SQLite store + TeamKPI + order durability
│   ├── runtime.py      # runtime + team orchestration + risk/recovery
│   └── strategy.py     # selection strategy
├── tests
│   └── test_team_runtime.py
├── main.py
├── dashboard.py
└── README.md
```

## 빠른 실행 (기본: Dry-run)

```bash
python main.py --provider openai
```

기본은 dry-run 모드이며 API 키가 없으면 브로커도 stub 모드로 동작합니다.

## API 키 설정

### LLM

```bash
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export GITHUB_TOKEN="..."
```

### Brokers

```bash
# Meritz
export MERITZ_API_KEY="..."
export MERITZ_API_SECRET="..."
export MERITZ_ACCOUNT_NO="..."

# Binance
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."
```

## 주요 옵션

- `--provider`: `openai | claude | copilot`
- `--model`: 모델 오버라이드
- `--live-api`: 실 LLM API 호출
- `--budget`: 시작 예산
- `--max-market-exposure-ratio`: 시장(주식/가상화폐)별 최대 익스포저 비율
- `--exploratory-budget-ratio`: 실험(탐색) 예산 비율
- `--lab-cycles`: 실행 전 research loop 반복 횟수
- `--db-path`: SQLite 파일 경로

## 영속성 데이터

`SQLiteStore`는 다음을 저장합니다.

- `task_runs`: 태스크별 담당자/비용/실현매출/상태/노트
- `positions`: 시장/심볼/주문 예산/상태
- `system_events`: 실행 이벤트(성공/실패/리스크 중단/복구 스캔)
- `order_intents`: 브로커 제출 전후 주문 의도(멱등키 포함)
- `order_executions`: 브로커 응답 스냅샷
- `team_kpi_snapshots`: 팀 KPI 시계열 스냅샷
- `hypotheses`: 수익 가설(thesis/evidence/confidence/status)
- `hypotheses`는 rejected 누적 시 archived로 자동 전환 가능
- `experiment_runs`: 가설 실험 결과(pnl/return/outcome/failure_reason)
- `income_mechanisms`: 투자 외 포함 수익 메커니즘 레지스트리
- `process_blueprints`: 메커니즘별 정형화 프로세스 블루프린트
- `automation_candidates`: 자동화 후보(type/status/confidence/reason)
- `candidate_assets`: 후보별 재사용 asset(prompt/script 등)
- `token_observations`: 후보별 token in/out/cost 관측치
- `token_policies`: task type별 token economy 정책
- `execution_route_logs`: 최근 실행 경로/절감량/에스컬레이션 이력
- `execution_cache`: 동일 입력 재사용 결과 캐시

또한 `team_kpis()`로 팀원별 task 수, 매출, 비용, 이익을 집계합니다.

## GUI 대시보드

모든 핵심 데이터를 조회/관리할 수 있는 웹 대시보드를 제공합니다.

```bash
python dashboard.py --db-path agent_state.db --port 8080 --username admin --password "change-me"
```

브라우저에서 `http://localhost:8080` 접속 후 다음을 수행할 수 있습니다.

- KPI/수익/비용/미체결 주문 현황 확인
- hypothesis status counts / top confidence hypotheses / recent experiments / lab summary 확인
- income mechanism 목록/상태 및 process blueprint 목록 확인
- automation candidate / token cost 요약 확인
- token policy / 최근 execution route / execution mode usage / estimated token savings 확인
- Task Runs / Positions / Order Intents / Executions / KPI Snapshots / Events 조회
- Order Executions `raw_response`에서 validation 보정/실패 사유 확인 가능
- 수동 관리 액션
  - KPI snapshot 생성
  - 주문 의도(`order_intents`) 상태 변경
  - 포지션 상태 변경
  - 수동 이벤트 기록
- 운영 하드닝
  - Basic Auth(`--username/--password` 또는 `DASHBOARD_USERNAME/DASHBOARD_PASSWORD`)
  - 보안 헤더(`X-Frame-Options`, `X-Content-Type-Options`)
  - JSON API(`/api/summary`) 제공
  - 입력 유효성 검증(상태값/쿼리 limit)

## 테스트

```bash
python -m unittest discover -s tests -v
```

## 참고

- `agent/brokers.py`의 메리츠 live 서명은 운영 전 최신 공식 문서의 헤더/파라미터 요구사항으로 최종 보정해야 합니다.
- Binance는 signed endpoint 기본 흐름(HMAC, timestamp, recvWindow)을 반영했지만, 실거래 전 주문 수량/정밀도/규정 필터(`LOT_SIZE`, `MIN_NOTIONAL`) 검증이 추가로 필요합니다.


## Distribution & Conversion Loop

- Distribution target registry for `blog_post`, `freelance_proposal`, `automation_offer`, `digital_product_offer`, `lead_list`, `outreach_message`.
- Channel registry for `blog`, `email`, `marketplace`, `landing_page`, `social`, `direct_outreach`.
- Distribution run tracking and conversion event persistence (impression/click/reply/lead/sale/rejected/no_response).
- Stub adapters (`BlogChannelAdapterStub`, `OutreachChannelAdapterStub`, `MarketplaceChannelAdapterStub`) to simulate external distribution without network dependencies.
- Feedback integration updates mechanism confidence/repeatability and recent hypothesis confidence from conversion outcomes.
- Dashboard/API now expose distribution targets/channels/runs/events and conversion metrics by channel/mechanism/target type plus token efficiency.
