from __future__ import annotations

import argparse
import base64
import json
import logging
import os
from dataclasses import dataclass
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from agent import AllocationScoringEngine, SQLiteStore

LOGGER = logging.getLogger("agent-dashboard")


@dataclass
class DashboardConfig:
    host: str
    port: int
    db_path: str
    username: str
    password: str


def _table(headers: list[str], rows: list[tuple]) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body_rows: list[str] = []
    for row in rows:
        tds = "".join(f"<td>{escape(str(cell))}</td>" for cell in row)
        body_rows.append(f"<tr>{tds}</tr>")
    body = "".join(body_rows) if body_rows else "<tr><td colspan='99'>No data</td></tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_dashboard(store: SQLiteStore, flash: str = "") -> str:
    metrics = store.summary_metrics()
    kpis = store.team_kpis()
    tasks = store.list_task_runs(50)
    positions = store.list_positions(50)
    intents = store.list_order_intents(50)
    executions = store.list_order_executions(50)
    snapshots = store.list_team_kpi_snapshots(50)
    events = list(store.recent_events(50))

    status_counts = store.hypothesis_status_counts()
    top_hypotheses = store.top_hypotheses_by_confidence(20)
    experiments = store.recent_experiment_runs(30)
    lab = store.lab_summary()
    mechanisms = store.list_income_mechanisms(30)
    mechanism_status = store.mechanism_status_counts()
    blueprints = store.list_process_blueprints(30)
    automation_candidates = store.list_automation_candidates(30)
    token_summary = store.token_observation_summary()
    token_policies = store.list_token_policies(30)
    execution_routes = store.recent_execution_routes(30)
    execution_mode_usage = store.execution_mode_usage()
    execution_savings = store.execution_savings_summary()
    distribution_targets = store.list_distribution_targets(30)
    distribution_channels = store.list_distribution_channels(30)
    distribution_runs = store.list_distribution_runs(30)
    conversion_events = store.list_conversion_events(30)
    channel_conversion = store.conversion_metrics_by_channel()
    mechanism_conversion = store.conversion_metrics_by_mechanism()
    target_conversion = store.conversion_metrics_by_target_type()
    dist_token_efficiency = store.distribution_token_efficiency()
    allocation_policies = store.list_allocation_policies(30)
    variants = store.list_offer_variants(limit=30)
    recommendations = store.list_allocation_recommendations(30)
    perf_by_channel = store.performance_summary(dimension="channel", limit=30)
    perf_by_mechanism = store.performance_summary(dimension="mechanism", limit=30)
    perf_by_variant = store.performance_summary(dimension="variant", limit=30)
    scoring_engine = AllocationScoringEngine(store)
    channel_scores = scoring_engine.score_dimension("channel", limit=20)

    kpi_rows = [(k.assignee, k.task_count, round(k.revenue, 2), round(k.cost, 2), round(k.profit, 2)) for k in kpis]

    return f"""
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta http-equiv="Cache-Control" content="no-store" />
  <title>Autonomous Profit Agent Dashboard</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: #0b1020; color: #e5e7eb; }}
    .container {{ max-width: 1300px; margin: 0 auto; padding: 24px; }}
    h1, h2 {{ margin: 0 0 12px 0; }}
    .muted {{ color: #9ca3af; }}
    .flash {{ background: #1d4ed8; padding: 10px 12px; border-radius: 8px; margin-bottom: 16px; }}
    .cards {{ display: grid; grid-template-columns: repeat(8, 1fr); gap: 12px; margin-bottom: 16px; }}
    .card {{ background: #111827; padding: 14px; border-radius: 10px; border: 1px solid #1f2937; }}
    .card .k {{ font-size: 12px; color: #9ca3af; }}
    .card .v {{ font-size: 20px; font-weight: 700; margin-top: 6px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    section {{ background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 14px; margin-bottom: 16px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ border-bottom: 1px solid #1f2937; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ color: #93c5fd; }}
    input, select {{ background: #0b1020; color: #e5e7eb; border: 1px solid #374151; border-radius: 6px; padding: 6px; }}
    button {{ background: #2563eb; color: #fff; border: 0; border-radius: 6px; padding: 7px 10px; cursor: pointer; }}
    form.inline {{ display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }}
  </style>
</head>
<body>
  <div class="container">
    <h1>Autonomous Profit Agent Dashboard</h1>
    <p class="muted">가설 생성 → 실험 → 학습 → 실행 상태를 한곳에서 조회/관리합니다.</p>
    {f'<div class="flash">{escape(flash)}</div>' if flash else ''}

    <div class="cards">
      <div class="card"><div class="k">Revenue</div><div class="v">{metrics['revenue']:.2f}</div></div>
      <div class="card"><div class="k">Cost</div><div class="v">{metrics['cost']:.2f}</div></div>
      <div class="card"><div class="k">Profit</div><div class="v">{metrics['profit']:.2f}</div></div>
      <div class="card"><div class="k">Pending Orders</div><div class="v">{metrics['pending_orders']}</div></div>
      <div class="card"><div class="k">Validated Hypothesis</div><div class="v">{metrics['validated_hypotheses']}</div></div>
      <div class="card"><div class="k">Rejected Hypothesis</div><div class="v">{metrics['rejected_hypotheses']}</div></div>
      <div class="card"><div class="k">Archived Hypothesis</div><div class="v">{metrics['archived_hypotheses']}</div></div>
      <div class="card"><div class="k">Experiment Avg Return</div><div class="v">{lab['avg_experiment_return_pct']:.2f}</div></div>
      <div class="card"><div class="k">Mechanisms</div><div class="v">{metrics['mechanism_count']}</div></div>
      <div class="card"><div class="k">Blueprints</div><div class="v">{metrics['blueprint_count']}</div></div>
      <div class="card"><div class="k">Automation Candidates</div><div class="v">{metrics['automation_candidate_count']}</div></div>
      <div class="card"><div class="k">Token Cost (USD)</div><div class="v">{token_summary['token_cost_usd']:.2f}</div></div>
      <div class="card"><div class="k">LLM Replaced</div><div class="v">{execution_savings['replaced_llm_count']}</div></div>
      <div class="card"><div class="k">Token Savings (est)</div><div class="v">{execution_savings['estimated_token_savings']}</div></div>
      <div class="card"><div class="k">Distribution Targets</div><div class="v">{metrics['distribution_target_count']}</div></div>
      <div class="card"><div class="k">Channels</div><div class="v">{metrics['distribution_channel_count']}</div></div>
      <div class="card"><div class="k">Distribution Runs</div><div class="v">{metrics['distribution_run_count']}</div></div>
      <div class="card"><div class="k">Conversion Events</div><div class="v">{metrics['conversion_event_count']}</div></div>
      <div class="card"><div class="k">Conv Revenue / Token</div><div class="v">{dist_token_efficiency['revenue_per_token']:.4f}</div></div>
      <div class="card"><div class="k">Allocation Policies</div><div class="v">{metrics['allocation_policy_count']}</div></div>
      <div class="card"><div class="k">Offer Variants</div><div class="v">{metrics['offer_variant_count']}</div></div>
      <div class="card"><div class="k">Recommendations</div><div class="v">{metrics['allocation_recommendation_count']}</div></div>
      <div class="card"><div class="k">Auto Applied Realloc</div><div class="v">{metrics['auto_applied_recommendation_count']}</div></div>
    </div>

    <section>
      <h2>관리 액션</h2>
      <form method="post" action="/action/snapshot_kpi" class="inline"><button type="submit">KPI Snapshot 생성</button></form>
      <br />
      <form method="post" action="/action/update_intent_status" class="inline">
        <label>Intent client_order_id</label><input name="client_order_id" required />
        <label>Status</label>
        <select name="status"><option>submitted</option><option>partial_fill</option><option>filled</option><option>canceled</option><option>rejected</option><option>rejected_validation</option></select>
        <button type="submit">Intent 상태 변경</button>
      </form>
      <br />
      <form method="post" action="/action/update_position_status" class="inline">
        <label>Position ID</label><input name="position_id" type="number" required />
        <label>Status</label>
        <select name="status"><option>submitted</option><option>open</option><option>closed</option><option>canceled</option></select>
        <button type="submit">Position 상태 변경</button>
      </form>
      <br />
      <form method="post" action="/action/create_event" class="inline">
        <label>Event Type</label><input name="event_type" value="manual_event" required />
        <label>Details</label><input name="details" size="50" required />
        <button type="submit">이벤트 기록</button>
      </form>
    </section>

    <div class="grid">
      <section><h2>Hypothesis Status Counts</h2>{_table(['status', 'count'], status_counts)}</section>
      <section><h2>Top Confidence Hypotheses</h2>{_table(['id','title','thesis','evidence','expected_edge','confidence','invalidation_rule','status','linked_key','updated_at'], top_hypotheses)}</section>
    </div>

    <section><h2>Recent Experiments</h2>{_table(['id','hypothesis_id','allocated_budget','result_pnl','result_return_pct','outcome','failure_reason','notes','started_at','completed_at'], experiments)}</section>

    <div class="grid">
      <section><h2>Income Mechanism Status</h2>{_table(['status','count'], mechanism_status)}</section>
      <section><h2>Income Mechanisms</h2>{_table(['id','type','title','expected_revenue','expected_cost','expected_token_cost','automation_potential','repeatability_score','maintenance_cost','current_stage','status','confidence','time_to_payout','created_at'], [(m[0],m[1],m[2],m[4],m[5],m[6],m[7],m[8],m[9],m[10],m[11],m[12],m[13],m[14]) for m in mechanisms])}</section>
    </div>

    <section><h2>Process Blueprints</h2>{_table(['id','mechanism_id','task_type','title','automation_status','estimated_token_cost','estimated_run_cost','reuse_count','created_at'], [(b[0],b[1],b[2],b[3],b[11],b[12],b[13],b[14],b[15]) for b in blueprints])}</section>
    <section><h2>Automation Candidates</h2>{_table(['id','mechanism_id','candidate_type','title','status','confidence','reason','updated_at'], [(c[0],c[1],c[2],c[3],c[4],c[5],c[6],c[8]) for c in automation_candidates])}</section>
    <section><h2>Token Policies</h2>{_table(['policy_id','task_type','mechanism_type','max_token_budget','preferred_mode','allow_llm_direct','escalation','fallback','caching'], [(p[0],p[1],p[2],p[4],p[5],p[6],p[7],p[8],p[9]) for p in token_policies])}</section>

    <div class="grid">
      <section><h2>Team KPI</h2>{_table(['assignee', 'task_count', 'revenue', 'cost', 'profit'], kpi_rows)}</section>
      <section><h2>최근 시스템 이벤트</h2>{_table(['id', 'event_type', 'details', 'created_at'], events)}</section>
    </div>

    <section><h2>Task Runs</h2>{_table(['id','task_id','assignee','channel','instrument','est_cost','realized_revenue','status','created_at'], tasks)}</section>
    <section><h2>Positions</h2>{_table(['id','market','symbol','budget','side','status','metadata','created_at'], positions)}</section>
    <section><h2>Order Intents</h2>{_table(['id','task_id','market','symbol','side','budget','client_order_id','status','created_at'], intents)}</section>
    <section><h2>Order Executions</h2>{_table(['id','client_order_id','broker','order_id','status','raw_response','created_at'], executions)}</section>
    <section><h2>KPI Snapshots</h2>{_table(['id','assignee','task_count','revenue','cost','profit','created_at'], snapshots)}</section>
    <section><h2>Execution Mode Usage</h2>{_table(['mode','count'], execution_mode_usage)}</section>
    <section><h2>Distribution Targets</h2>{_table(['id','mechanism_id','blueprint_id','asset_id','target_type','title','summary','payload_json','status','created_at'], distribution_targets)}</section>
    <section><h2>Distribution Channels</h2>{_table(['id','channel_type','name','description','config_json','is_active','created_at'], distribution_channels)}</section>
    <section><h2>Recent Distribution Runs</h2>{_table(['id','target_id','channel_id','mechanism_id','execution_mode','status','external_ref','submitted_at','completed_at','notes'], distribution_runs)}</section>
    <section><h2>Conversion Events</h2>{_table(['id','run_id','target_id','mechanism_id','event_type','value_estimate','metadata_json','occurred_at'], conversion_events)}</section>
    <section><h2>Channel Conversion Metrics</h2>{_table(['channel','submitted','response_rate','conversion_rate','revenue_estimate'], channel_conversion)}</section>
    <section><h2>Mechanism Conversion Metrics</h2>{_table(['id','type','title','conversions','revenue_estimate'], mechanism_conversion)}</section>
    <section><h2>Target Type Performance</h2>{_table(['target_type','runs','conversions','revenue_estimate'], target_conversion)}</section>
    <section><h2>Distribution Token Efficiency</h2>{_table(['conversion_count','estimated_revenue','token_spend_estimate','revenue_per_token'], [(dist_token_efficiency['conversion_count'], dist_token_efficiency['estimated_revenue'], dist_token_efficiency['token_spend_estimate'], dist_token_efficiency['revenue_per_token'])])}</section>
    <section><h2>Allocation Policies</h2>{_table(['id','mechanism_id','channel_id','target_type','execution_mode','base_weight','min_trials','max_trials','cooldown_hours','is_active','updated_at'], allocation_policies)}</section>
    <section><h2>Offer Variants</h2>{_table(['id','target_id','variant_key','title','payload_patch_json','status','created_at'], variants)}</section>
    <section><h2>Channel Allocation Score Breakdown</h2>{_table(['channel_key','score','conversion_rate','response_rate','est_revenue','revenue_per_token','failure_rate','no_response_rate','repeatability','automation_potential','execution_cost','token_cost'], [(x.key, x.score, x.conversion_rate, x.response_rate, x.estimated_revenue, x.revenue_per_token, x.failure_rate, x.no_response_rate, x.repeatability_score, x.automation_potential, x.execution_cost, x.token_cost) for x in channel_scores])}</section>
    <section><h2>Performance by Channel</h2>{_table(['key','submissions','deliveries','responses','conversions','estimated_revenue','response_rate','conversion_rate','revenue_per_run','revenue_per_token','conversion_per_token','failure_rate','no_response_rate','repeatability','automation','execution_cost','token_cost'], perf_by_channel)}</section>
    <section><h2>Performance by Mechanism</h2>{_table(['key','submissions','deliveries','responses','conversions','estimated_revenue','response_rate','conversion_rate','revenue_per_run','revenue_per_token','conversion_per_token','failure_rate','no_response_rate','repeatability','automation','execution_cost','token_cost'], perf_by_mechanism)}</section>
    <section><h2>Performance by Variant</h2>{_table(['key','submissions','deliveries','responses','conversions','estimated_revenue','response_rate','conversion_rate','revenue_per_run','revenue_per_token','conversion_per_token','failure_rate','no_response_rate','repeatability','automation','execution_cost','token_cost'], perf_by_variant)}</section>
    <section><h2>Reallocation Recommendations</h2>{_table(['id','mechanism_id','channel_id','target_type','variant_id','recommendation_type','rationale','expected_impact','confidence','status','auto_applied','created_at'], recommendations)}</section>
    <section><h2>Recent Execution Routes</h2>{_table(['id','task_id','task_type','mechanism_type','selected_mode','fallback_mode','reason','token_cost','token_savings','escalated','status','created_at'], execution_routes)}</section>
  </div>
</body>
</html>
"""


def _basic_auth_value(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def create_handler(store: SQLiteStore, config: DashboardConfig):
    class DashboardHandler(BaseHTTPRequestHandler):
        def _is_authorized(self) -> bool:
            if not config.username:
                return True
            return self.headers.get("Authorization", "") == _basic_auth_value(config.username, config.password)

        def _require_auth(self) -> bool:
            if self._is_authorized():
                return True
            self.send_response(HTTPStatus.UNAUTHORIZED)
            self.send_header("WWW-Authenticate", 'Basic realm="Agent Dashboard"')
            self.end_headers()
            return False

        def _read_form(self) -> dict[str, str]:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 10_000:
                raise ValueError("request body too large")
            body = self.rfile.read(length).decode("utf-8") if length else ""
            parsed = parse_qs(body)
            return {k: v[0] for k, v in parsed.items()}

        def _redirect(self, message: str = "") -> None:
            target = "/"
            if message:
                target += f"?flash={message}"
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", target)
            self.end_headers()

        def _send_json(self, payload: dict) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self) -> None:  # noqa: N802
            if not self._require_auth():
                return
            parsed = urlparse(self.path)
            if parsed.path == "/api/summary":
                self._send_json(
                    {
                        "metrics": store.summary_metrics(),
                        "team_kpis": [k.__dict__ for k in store.team_kpis()],
                        "hypothesis_status_counts": store.hypothesis_status_counts(),
                        "recent_experiments": store.recent_experiment_runs(10),
                        "top_hypotheses": store.top_hypotheses_by_confidence(10),
                        "lab_summary": store.lab_summary(),
                        "mechanism_status_counts": store.mechanism_status_counts(),
                        "income_mechanisms": store.list_income_mechanisms(20),
                        "process_blueprints": store.list_process_blueprints(20),
                        "automation_candidates": store.list_automation_candidates(20),
                        "token_observation_summary": store.token_observation_summary(),
                        "token_policies": store.list_token_policies(50),
                        "recent_execution_routes": store.recent_execution_routes(50),
                        "execution_mode_usage": store.execution_mode_usage(),
                        "execution_savings_summary": store.execution_savings_summary(),
                        "distribution_targets": store.list_distribution_targets(50),
                        "distribution_channels": store.list_distribution_channels(50),
                        "distribution_runs": store.list_distribution_runs(50),
                        "conversion_events": store.list_conversion_events(50),
                        "channel_conversion_metrics": store.conversion_metrics_by_channel(),
                        "mechanism_conversion_metrics": store.conversion_metrics_by_mechanism(),
                        "target_conversion_metrics": store.conversion_metrics_by_target_type(),
                        "distribution_token_efficiency": store.distribution_token_efficiency(),
                        "allocation_policies": store.list_allocation_policies(50),
                        "offer_variants": store.list_offer_variants(limit=50),
                        "allocation_recommendations": store.list_allocation_recommendations(50),
                        "performance_by_channel": store.performance_summary(dimension="channel", limit=50),
                        "performance_by_mechanism": store.performance_summary(dimension="mechanism", limit=50),
                        "performance_by_target_type": store.performance_summary(dimension="target_type", limit=50),
                        "performance_by_execution_mode": store.performance_summary(dimension="execution_mode", limit=50),
                        "performance_by_variant": store.performance_summary(dimension="variant", limit=50),
                        "allocation_channel_scores": [x.__dict__ for x in AllocationScoringEngine(store).score_dimension("channel", limit=50)],
                    }
                )
                return
            if parsed.path != "/":
                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()
                return
            flash = parse_qs(parsed.query).get("flash", [""])[0]
            html = render_dashboard(store, flash=flash)
            encoded = html.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(encoded)

        def do_POST(self) -> None:  # noqa: N802
            if not self._require_auth():
                return
            parsed = urlparse(self.path)
            try:
                form = self._read_form()
                if parsed.path == "/action/snapshot_kpi":
                    store.snapshot_team_kpis()
                    self._redirect("KPI snapshot created")
                    return
                if parsed.path == "/action/update_intent_status":
                    ok = store.update_order_intent_status(form.get("client_order_id", ""), form.get("status", "submitted"))
                    self._redirect("Intent status updated" if ok else "Intent not found")
                    return
                if parsed.path == "/action/update_position_status":
                    position_id = int(form.get("position_id", "0"))
                    ok = store.update_position_status(position_id, form.get("status", "submitted")) if position_id > 0 else False
                    self._redirect("Position status updated" if ok else "Position not found")
                    return
                if parsed.path == "/action/create_event":
                    store.record_event(form.get("event_type", "manual_event"), form.get("details", ""))
                    self._redirect("Event recorded")
                    return

                self.send_response(HTTPStatus.NOT_FOUND)
                self.end_headers()
            except Exception as exc:  # noqa: BLE001
                LOGGER.exception("dashboard action failed: %s", exc)
                self._redirect(f"Action failed: {exc}")

        def log_message(self, fmt: str, *args) -> None:  # noqa: A003
            LOGGER.info("dashboard %s - %s", self.address_string(), fmt % args)

    return DashboardHandler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Autonomous Profit Agent Dashboard")
    parser.add_argument("--db-path", default="agent_state.db")
    parser.add_argument("--host", default=os.getenv("DASHBOARD_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("DASHBOARD_PORT", "8080")))
    parser.add_argument("--username", default=os.getenv("DASHBOARD_USERNAME", ""))
    parser.add_argument("--password", default=os.getenv("DASHBOARD_PASSWORD", ""))
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = parse_args()
    cfg = DashboardConfig(
        host=args.host,
        port=args.port,
        db_path=args.db_path,
        username=args.username,
        password=args.password,
    )
    if cfg.username and not cfg.password:
        raise ValueError("Dashboard password is required when username is set")

    store = SQLiteStore(db_path=cfg.db_path)
    handler = create_handler(store, cfg)
    server = ThreadingHTTPServer((cfg.host, cfg.port), handler)
    LOGGER.info("Dashboard running on http://%s:%s (db=%s)", cfg.host, cfg.port, cfg.db_path)
    server.serve_forever()


if __name__ == "__main__":
    main()
