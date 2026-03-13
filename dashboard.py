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

from agent import SQLiteStore

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
    .cards {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 16px; }}
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
    <p class="muted">실행 상태, 주문, 포지션, 이벤트를 한곳에서 조회/관리합니다.</p>
    {f'<div class="flash">{escape(flash)}</div>' if flash else ''}

    <div class="cards">
      <div class="card"><div class="k">Revenue</div><div class="v">{metrics['revenue']:.2f}</div></div>
      <div class="card"><div class="k">Cost</div><div class="v">{metrics['cost']:.2f}</div></div>
      <div class="card"><div class="k">Profit</div><div class="v">{metrics['profit']:.2f}</div></div>
      <div class="card"><div class="k">Pending Orders</div><div class="v">{metrics['pending_orders']}</div></div>
    </div>

    <section>
      <h2>관리 액션</h2>
      <form method="post" action="/action/snapshot_kpi" class="inline"><button type="submit">KPI Snapshot 생성</button></form>
      <br />
      <form method="post" action="/action/update_intent_status" class="inline">
        <label>Intent client_order_id</label><input name="client_order_id" required />
        <label>Status</label>
        <select name="status"><option>submitted</option><option>partial_fill</option><option>filled</option><option>canceled</option><option>rejected</option></select>
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
      <section><h2>Team KPI (실시간 집계)</h2>{_table(['assignee', 'task_count', 'revenue', 'cost', 'profit'], kpi_rows)}</section>
      <section><h2>최근 시스템 이벤트</h2>{_table(['id', 'event_type', 'details', 'created_at'], events)}</section>
    </div>

    <section><h2>Task Runs</h2>{_table(['id','task_id','assignee','channel','instrument','est_cost','realized_revenue','status','created_at'], tasks)}</section>
    <section><h2>Positions</h2>{_table(['id','market','symbol','budget','side','status','metadata','created_at'], positions)}</section>
    <section><h2>Order Intents</h2>{_table(['id','task_id','market','symbol','side','budget','client_order_id','status','created_at'], intents)}</section>
    <section><h2>Order Executions</h2>{_table(['id','client_order_id','broker','order_id','status','raw_response','created_at'], executions)}</section>
    <section><h2>KPI Snapshots</h2>{_table(['id','assignee','task_count','revenue','cost','profit','created_at'], snapshots)}</section>
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
                self._send_json({"metrics": store.summary_metrics(), "team_kpis": [k.__dict__ for k in store.team_kpis()]})
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
