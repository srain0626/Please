# Autonomous Profit Agent (PoC)

브라우저/명령 실행 환경을 가진 에이전트가 **수익 기회 탐색 → 실험 → 실행 → 학습 → 최적화**를 반복하는 프로젝트입니다.

이 저장소는 단순 트레이딩 봇이 아니라, 아래 루프를 한 프레임에서 다룹니다.

1. 기회 생성(팩토리)  
2. 가설/실험(Strategy Lab)  
3. 실행 라우팅(Token Economy + Execution Router)  
4. 외부 배포/전환(Distribution & Conversion)  
5. 채널/오퍼 배분 최적화(Allocation)  
6. 오퍼 자체 자기개선(Self-Improvement)

---

## 1) 핵심 개념

### Strategy Lab
- `Opportunity`를 바로 실행하지 않고 가설(`hypotheses`)로 승격
- 소액 실험(`experiment_runs`) 수행
- 성과 기반으로 `proposed/testing/validated/rejected/archived` 전환

### Execution Router
- 실행 모드: `llm_direct | prompt_template | rule_based | code_based`
- 원칙: **cheap-first / deterministic-first / reusable-first**
- 토큰 정책(`token_policies`) + 캐시(`execution_cache`) + 라우팅 로그(`execution_route_logs`) 지원

### Distribution & Conversion
- 배포 대상(`distribution_targets`) / 채널(`distribution_channels`) / 실행 이력(`distribution_runs`) / 외부 반응(`conversion_events`) 저장
- stub adapter로 네트워크 없이 시뮬레이션 가능

### Allocation Optimization
- 성과 집계를 기반으로 채널/타깃/실행모드 배분 추천 생성
- `allocation_policies`, `allocation_recommendations`, `offer_variants` 관리

### Offer Self-Improvement
- 변형 생성기(`VariantGenerator`)로 headline/CTA/length/structure/execution mode mutation 생성
- 실험 큐(`variant_experiment_queue`)에서 소규모 검증
- 비교기(`VariantPerformanceComparator`)로 승격/폐기 판단
- 개선 추천(`creative_recommendations`) 생성

---

## 2) 빠른 시작

### 설치
별도 패키지 설치 없이 Python 표준 라이브러리 기반으로 실행 가능합니다.

### 기본 실행 (Dry-run)
```bash
python main.py --provider openai
```

### Gemini 실행 예시
```bash
# 1) API key 방식
export GEMINI_API_KEY="..."
python main.py --provider gemini --live-api --gemini-auth api_key

# 2) Gemini CLI 로그인 방식
# 먼저 로컬에서 gemini CLI 로그인을 완료한 뒤
python main.py --provider gemini --live-api --gemini-auth cli
```

### 주요 옵션
- `--provider`: `openai | claude | copilot | gemini`
- `--gemini-auth`: `auto | api_key | cli`
- `--model`: 모델명 오버라이드
- `--live-api`: 실제 LLM API 호출
- `--budget`: 시작 예산
- `--max-market-exposure-ratio`: 시장별 최대 익스포저
- `--exploratory-budget-ratio`: 탐색/실험 예산 비율
- `--lab-cycles`: Strategy Lab 반복 횟수
- `--db-path`: SQLite 파일 경로

---

## 3) 환경 변수

### LLM
```bash
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export GITHUB_TOKEN="..."
export GEMINI_API_KEY="..."
# 또는 일부 환경에서는 GOOGLE_API_KEY 사용 가능
export GOOGLE_API_KEY="..."
```

### Broker
```bash
# Meritz
export MERITZ_API_KEY="..."
export MERITZ_API_SECRET="..."
export MERITZ_ACCOUNT_NO="..."

# Binance
export BINANCE_API_KEY="..."
export BINANCE_API_SECRET="..."
```

> 키가 없으면 기본적으로 안전한 stub/dry-run 경로를 사용합니다. Gemini는 `--gemini-auth auto`일 때 **API key가 있으면 API key 우선**, 없고 `gemini` CLI가 PATH에 있으면 **CLI 인증 경로**를 사용합니다.

---

## 4) 대시보드 사용법

```bash
python dashboard.py --db-path agent_state.db --port 8080 --username admin --password "change-me"
```

접속: `http://localhost:8080`

### 대시보드에서 볼 수 있는 내용
- 수익/비용/ROI/KPI/이벤트
- 가설/실험 상태
- 메커니즘/블루프린트/자동화 후보
- 토큰 정책/실행 라우팅/절감량
- 배포 대상/채널/실행/전환 지표
- 배분 정책/추천/오퍼 variant 비교
- variant 실험 큐/승격·폐기 이력/creative 개선 추천

### 관리 액션
- KPI snapshot 생성
- 주문 의도 상태 변경
- 포지션 상태 변경
- 수동 이벤트 기록

---

## 5) 실행 루프 요약

### 내부 루프
1. Opportunity 생성
2. Hypothesis 생성
3. Small-bet experiment
4. Confidence 업데이트
5. Validated 전략 실행

### 외부 성과 루프
1. Target 생성
2. Channel 배포
3. Response/Conversion 이벤트 기록
4. Allocation 추천 생성
5. Self-improvement variant 생성/검증/승격

---

## 6) 데이터 저장소(SQLite)

핵심 테이블 묶음:

### 연구/전략
- `hypotheses`, `experiment_runs`

### 실행/거래
- `task_runs`, `positions`, `order_intents`, `order_executions`, `system_events`

### 메커니즘/프로세스
- `income_mechanisms`, `process_blueprints`

### 자동화/토큰
- `automation_candidates`, `candidate_assets`, `token_observations`, `token_policies`, `execution_route_logs`, `execution_cache`

### 배포/전환
- `distribution_targets`, `distribution_channels`, `distribution_runs`, `conversion_events`

### 최적화/자기개선
- `allocation_policies`, `offer_variants`, `allocation_recommendations`, `variant_experiment_queue`, `creative_recommendations`

---

## 7) 테스트

```bash
python -m unittest discover -s tests -v
```

테스트는 allocation/distribution/router/lab/order-validation/self-improvement/runtime까지 포함합니다.

---

## 8) 프로젝트 구조

```text
.
├── agent/
│   ├── brokers.py
│   ├── execution.py
│   ├── lab.py
│   ├── distribution.py
│   ├── allocation.py
│   ├── self_improvement.py
│   ├── persistence.py
│   ├── runtime.py
│   ├── strategy.py
│   ├── llm.py
│   ├── mechanisms.py
│   └── models.py
├── dashboard.py
├── main.py
└── tests/
```

---

## 9) 운영 시 주의사항

- Meritz/Binance 실거래 사용 전, 최신 API 스펙/서명 규칙/에러 코드/주문 제한을 반드시 재검증하세요.
- 이 저장소는 PoC 성격이며, 실거래 적용 전에는 리스크 한도·재시도·모니터링·장애복구 정책을 강화해야 합니다.
- 추천/자동 상태 전이는 규칙 기반이므로, 운영 환경에서는 사람 승인(approval gate)과 함께 사용하는 것을 권장합니다.
