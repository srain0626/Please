from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .mechanisms import MECHANISM_TYPES
from .models import OpportunityType, Task

ORDER_INTENT_STATUSES = {
    "submitted",
    "partial_fill",
    "filled",
    "canceled",
    "rejected",
    "rejected_validation",
    "stub_submitted",
}
POSITION_STATUSES = {"submitted", "open", "closed", "canceled"}
HYPOTHESIS_STATUSES = {"proposed", "testing", "validated", "rejected", "archived"}
MECHANISM_STATUSES = {"active", "paused", "deprecated", "testing"}
AUTOMATION_CANDIDATE_STATUSES = {"proposed", "evaluating", "active", "paused", "retired"}
EXECUTION_MODES = {"llm_direct", "prompt_template", "rule_based", "code_based"}


@dataclass
class TeamKPI:
    assignee: str
    task_count: int
    revenue: float
    cost: float

    @property
    def profit(self) -> float:
        return self.revenue - self.cost


class SQLiteStore:
    def __init__(self, db_path: str = "agent_state.db") -> None:
        self.db_path = Path(db_path)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER,
                    assignee TEXT,
                    channel TEXT,
                    instrument TEXT,
                    estimated_cost REAL,
                    realized_revenue REAL,
                    status TEXT,
                    notes TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    market TEXT,
                    symbol TEXT,
                    budget REAL,
                    side TEXT,
                    status TEXT,
                    metadata TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS system_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT,
                    details TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS order_intents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER,
                    market TEXT,
                    symbol TEXT,
                    side TEXT,
                    budget REAL,
                    client_order_id TEXT UNIQUE,
                    status TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS order_executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_order_id TEXT,
                    broker TEXT,
                    order_id TEXT,
                    status TEXT,
                    raw_response TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS team_kpi_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    assignee TEXT,
                    task_count INTEGER,
                    revenue REAL,
                    cost REAL,
                    profit REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hypotheses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    thesis TEXT,
                    evidence TEXT,
                    expected_edge REAL,
                    confidence_score REAL,
                    invalidation_rule TEXT,
                    status TEXT,
                    linked_opportunity_key TEXT UNIQUE,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experiment_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hypothesis_id INTEGER,
                    allocated_budget REAL,
                    result_pnl REAL,
                    result_return_pct REAL,
                    outcome TEXT,
                    failure_reason TEXT,
                    notes TEXT,
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS income_mechanisms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT,
                    title TEXT,
                    description TEXT,
                    expected_revenue REAL,
                    expected_cost REAL,
                    expected_token_cost REAL,
                    automation_potential REAL,
                    repeatability_score REAL,
                    maintenance_cost REAL,
                    current_stage TEXT,
                    status TEXT,
                    confidence_score REAL DEFAULT 0.5,
                    time_to_payout REAL DEFAULT 0.5,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS process_blueprints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mechanism_id INTEGER,
                    task_type TEXT,
                    title TEXT,
                    description TEXT,
                    inputs_schema TEXT,
                    output_schema TEXT,
                    steps_json TEXT,
                    can_be_templated INTEGER,
                    can_be_ruled INTEGER,
                    can_be_coded INTEGER,
                    automation_status TEXT,
                    estimated_token_cost REAL,
                    estimated_run_cost REAL,
                    reuse_count INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS automation_candidates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mechanism_id INTEGER,
                    candidate_type TEXT,
                    title TEXT,
                    status TEXT,
                    confidence_score REAL,
                    reason TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(mechanism_id, candidate_type)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS candidate_assets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id INTEGER,
                    asset_key TEXT,
                    asset_kind TEXT,
                    payload TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS token_observations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    candidate_id INTEGER,
                    tokens_in INTEGER,
                    tokens_out INTEGER,
                    cost_usd REAL,
                    observed_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS token_policies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type TEXT,
                    mechanism_type TEXT,
                    mechanism_id INTEGER,
                    max_token_budget INTEGER,
                    preferred_execution_mode TEXT,
                    allow_llm_direct INTEGER,
                    escalation_condition TEXT,
                    fallback_mode TEXT,
                    caching_enabled INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_route_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id INTEGER,
                    task_type TEXT,
                    mechanism_type TEXT,
                    mechanism_id INTEGER,
                    selected_mode TEXT,
                    fallback_mode TEXT,
                    selected_reason TEXT,
                    estimated_token_cost INTEGER,
                    estimated_token_savings INTEGER,
                    escalated INTEGER,
                    status TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS execution_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cache_key TEXT UNIQUE,
                    task_type TEXT,
                    execution_mode TEXT,
                    input_hash TEXT,
                    output TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _validate_limit(self, limit: int) -> int:
        return max(1, min(limit, 1000))

    def _validate_order_intent_status(self, status: str) -> str:
        normalized = status.lower().strip()
        if normalized not in ORDER_INTENT_STATUSES:
            raise ValueError(f"invalid order intent status: {status}")
        return normalized

    def _validate_position_status(self, status: str) -> str:
        normalized = status.lower().strip()
        if normalized not in POSITION_STATUSES:
            raise ValueError(f"invalid position status: {status}")
        return normalized

    def _validate_hypothesis_status(self, status: str) -> str:
        normalized = status.lower().strip()
        if normalized not in HYPOTHESIS_STATUSES:
            raise ValueError(f"invalid hypothesis status: {status}")
        return normalized

    def _validate_mechanism_type(self, mechanism_type: str) -> str:
        normalized = mechanism_type.lower().strip()
        if normalized not in MECHANISM_TYPES:
            raise ValueError(f"invalid mechanism type: {mechanism_type}")
        return normalized

    def _validate_mechanism_status(self, status: str) -> str:
        normalized = status.lower().strip()
        if normalized not in MECHANISM_STATUSES:
            raise ValueError(f"invalid mechanism status: {status}")
        return normalized

    def _validate_automation_candidate_status(self, status: str) -> str:
        normalized = status.lower().strip()
        if normalized not in AUTOMATION_CANDIDATE_STATUSES:
            raise ValueError(f"invalid automation candidate status: {status}")
        return normalized

    def _validate_execution_mode(self, mode: str) -> str:
        normalized = mode.lower().strip()
        if normalized not in EXECUTION_MODES:
            raise ValueError(f"invalid execution mode: {mode}")
        return normalized

    def record_task_run(self, task: Task, assignee: str, realized_revenue: float) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO task_runs(task_id, assignee, channel, instrument, estimated_cost, realized_revenue, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.id,
                    assignee,
                    task.channel.value,
                    task.instrument,
                    task.estimated_cost,
                    realized_revenue,
                    task.status.value,
                    task.notes,
                ),
            )

    def record_position(
        self,
        market: OpportunityType,
        symbol: str,
        budget: float,
        side: str,
        status: str,
        metadata: str,
    ) -> None:
        valid_status = self._validate_position_status(status)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO positions(market, symbol, budget, side, status, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (market.value, symbol, budget, side, valid_status, metadata),
            )

    def record_order_intent(
        self,
        task_id: int,
        market: OpportunityType,
        symbol: str,
        side: str,
        budget: float,
        client_order_id: str,
        status: str,
    ) -> None:
        valid_status = self._validate_order_intent_status(status)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO order_intents(task_id, market, symbol, side, budget, client_order_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_order_id) DO UPDATE SET status=excluded.status
                """,
                (task_id, market.value, symbol, side, budget, client_order_id, valid_status),
            )

    def record_order_execution(
        self,
        client_order_id: str,
        broker: str,
        order_id: str,
        status: str,
        raw_response: str,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO order_executions(client_order_id, broker, order_id, status, raw_response)
                VALUES (?, ?, ?, ?, ?)
                """,
                (client_order_id, broker, order_id, status, raw_response),
            )

    def update_order_intent_status(self, client_order_id: str, status: str) -> bool:
        valid_status = self._validate_order_intent_status(status)
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE order_intents SET status=? WHERE client_order_id=?",
                (valid_status, client_order_id),
            )
        return cur.rowcount > 0

    def pending_order_intents(self) -> list[tuple[str, str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT market, symbol, client_order_id
                FROM order_intents
                WHERE status IN ('submitted', 'partial_fill')
                ORDER BY id ASC
                """
            ).fetchall()
        return rows

    def latest_execution_order_id(self, client_order_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT order_id
                FROM order_executions
                WHERE client_order_id=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (client_order_id,),
            ).fetchone()
        if not row:
            return None
        return str(row[0]) if row[0] else None

    def record_event(self, event_type: str, details: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO system_events(event_type, details) VALUES (?, ?)",
                (event_type, details),
            )

    def team_kpis(self) -> list[TeamKPI]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT assignee,
                       COUNT(*) as task_count,
                       COALESCE(SUM(realized_revenue), 0) as revenue,
                       COALESCE(SUM(estimated_cost), 0) as cost
                FROM task_runs
                GROUP BY assignee
                ORDER BY (COALESCE(SUM(realized_revenue), 0) - COALESCE(SUM(estimated_cost), 0)) DESC
                """
            ).fetchall()
        return [TeamKPI(assignee=r[0], task_count=r[1], revenue=r[2], cost=r[3]) for r in rows]

    def snapshot_team_kpis(self) -> None:
        kpis = self.team_kpis()
        with self._connect() as conn:
            for kpi in kpis:
                conn.execute(
                    """
                    INSERT INTO team_kpi_snapshots(assignee, task_count, revenue, cost, profit)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (kpi.assignee, kpi.task_count, kpi.revenue, kpi.cost, kpi.profit),
                )

    # ===== Research Loop Persistence =====
    def upsert_hypothesis(
        self,
        *,
        title: str,
        thesis: str,
        evidence: str,
        expected_edge: float,
        confidence_score: float,
        invalidation_rule: str,
        status: str,
        linked_opportunity_key: str,
    ) -> int:
        valid_status = self._validate_hypothesis_status(status)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM hypotheses WHERE linked_opportunity_key=?",
                (linked_opportunity_key,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE hypotheses
                    SET title=?, thesis=?, evidence=?, expected_edge=?,
                        confidence_score=?, invalidation_rule=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (title, thesis, evidence, expected_edge, confidence_score, invalidation_rule, int(existing[0])),
                )
                return int(existing[0])

            cur = conn.execute(
                """
                INSERT INTO hypotheses(title, thesis, evidence, expected_edge, confidence_score, invalidation_rule, status, linked_opportunity_key)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    title,
                    thesis,
                    evidence,
                    expected_edge,
                    confidence_score,
                    invalidation_rule,
                    valid_status,
                    linked_opportunity_key,
                ),
            )
            return int(cur.lastrowid)

    def update_hypothesis_state(self, *, hypothesis_id: int, confidence_score: float, status: str) -> None:
        valid_status = self._validate_hypothesis_status(status)
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE hypotheses
                SET confidence_score=?, status=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (max(0.0, min(1.0, confidence_score)), valid_status, hypothesis_id),
            )

    def list_hypotheses(self, statuses: list[str] | None = None, limit: int = 100) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            if statuses:
                normalized = [self._validate_hypothesis_status(s) for s in statuses]
                placeholders = ",".join("?" for _ in normalized)
                return conn.execute(
                    f"""
                    SELECT id, title, thesis, evidence, expected_edge, confidence_score, invalidation_rule, status, linked_opportunity_key, updated_at
                    FROM hypotheses
                    WHERE status IN ({placeholders})
                    ORDER BY confidence_score DESC, id DESC
                    LIMIT ?
                    """,
                    (*normalized, safe_limit),
                ).fetchall()
            return conn.execute(
                """
                SELECT id, title, thesis, evidence, expected_edge, confidence_score, invalidation_rule, status, linked_opportunity_key, updated_at
                FROM hypotheses
                ORDER BY confidence_score DESC, id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def hypothesis_status_counts(self) -> list[tuple[str, int]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*)
                FROM hypotheses
                GROUP BY status
                ORDER BY COUNT(*) DESC
                """
            ).fetchall()
        return [(str(r[0]), int(r[1])) for r in rows]

    def top_hypotheses_by_confidence(self, limit: int = 10) -> list[tuple]:
        return self.list_hypotheses(statuses=["validated", "testing", "proposed"], limit=limit)

    def record_experiment_run(
        self,
        *,
        hypothesis_id: int,
        allocated_budget: float,
        result_pnl: float,
        result_return_pct: float,
        outcome: str,
        failure_reason: str,
        notes: str,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO experiment_runs(hypothesis_id, allocated_budget, result_pnl, result_return_pct, outcome, failure_reason, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (hypothesis_id, allocated_budget, result_pnl, result_return_pct, outcome, failure_reason, notes),
            )
            return int(cur.lastrowid)

    def recent_experiment_runs(self, limit: int = 50) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, hypothesis_id, allocated_budget, result_pnl, result_return_pct, outcome, failure_reason, notes, started_at, completed_at
                FROM experiment_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def recent_success_patterns(self, limit: int = 10) -> list[tuple[str, str, float, float]]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT channel, instrument,
                       AVG(estimated_cost) as avg_cost,
                       AVG(realized_revenue) as avg_revenue
                FROM task_runs
                WHERE status='done'
                GROUP BY channel, instrument
                HAVING AVG(realized_revenue) > AVG(estimated_cost)
                ORDER BY (AVG(realized_revenue)-AVG(estimated_cost)) DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [(str(r[0]), str(r[1] or ""), float(r[2]), float(r[3])) for r in rows]

    def hypothesis_experiment_stats(self, hypothesis_id: int) -> tuple[int, int, float]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*),
                       COALESCE(SUM(CASE WHEN outcome='success' THEN 1 ELSE 0 END), 0),
                       COALESCE(AVG(result_return_pct), 0)
                FROM experiment_runs
                WHERE hypothesis_id=?
                """,
                (hypothesis_id,),
            ).fetchone()
        if not row:
            return 0, 0, 0.0
        return int(row[0]), int(row[1]), float(row[2])

    def archive_old_rejected_hypotheses(self, min_experiments: int = 3) -> int:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT h.id
                FROM hypotheses h
                JOIN experiment_runs e ON e.hypothesis_id = h.id
                WHERE h.status='rejected'
                GROUP BY h.id
                HAVING COUNT(e.id) >= ?
                """,
                (min_experiments,),
            ).fetchall()
            updated = 0
            for (hypothesis_id,) in rows:
                cur = conn.execute(
                    "UPDATE hypotheses SET status='archived', updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (int(hypothesis_id),),
                )
                updated += cur.rowcount
        return updated

    def lab_summary(self) -> dict[str, float]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as hypothesis_total,
                    COALESCE(SUM(CASE WHEN status='validated' THEN 1 ELSE 0 END), 0) as validated_count,
                    COALESCE(SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END), 0) as rejected_count,
                    COALESCE(SUM(CASE WHEN status='testing' THEN 1 ELSE 0 END), 0) as testing_count
                FROM hypotheses
                """
            ).fetchone()
            exp = conn.execute(
                """
                SELECT COUNT(*), COALESCE(AVG(result_return_pct), 0), COALESCE(SUM(result_pnl), 0)
                FROM experiment_runs
                """
            ).fetchone()
        return {
            "hypothesis_total": int(row[0]) if row else 0,
            "validated_count": int(row[1]) if row else 0,
            "rejected_count": int(row[2]) if row else 0,
            "testing_count": int(row[3]) if row else 0,
            "experiment_count": int(exp[0]) if exp else 0,
            "avg_experiment_return_pct": float(exp[1]) if exp else 0.0,
            "total_experiment_pnl": float(exp[2]) if exp else 0.0,
        }

    # ===== Income Mechanism Registry / Process Blueprint =====
    def create_income_mechanism(
        self,
        *,
        mechanism_type: str,
        title: str,
        description: str,
        expected_revenue: float,
        expected_cost: float,
        expected_token_cost: float,
        automation_potential: float,
        repeatability_score: float,
        maintenance_cost: float,
        current_stage: str,
        status: str,
        confidence_score: float = 0.5,
        time_to_payout: float = 0.5,
    ) -> int:
        mechanism_type = self._validate_mechanism_type(mechanism_type)
        status = self._validate_mechanism_status(status)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO income_mechanisms(
                    type, title, description, expected_revenue, expected_cost, expected_token_cost,
                    automation_potential, repeatability_score, maintenance_cost, current_stage, status,
                    confidence_score, time_to_payout
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mechanism_type,
                    title,
                    description,
                    expected_revenue,
                    expected_cost,
                    expected_token_cost,
                    automation_potential,
                    repeatability_score,
                    maintenance_cost,
                    current_stage,
                    status,
                    confidence_score,
                    time_to_payout,
                ),
            )
            return int(cur.lastrowid)

    def list_income_mechanisms(self, limit: int = 100) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, type, title, description, expected_revenue, expected_cost, expected_token_cost,
                       automation_potential, repeatability_score, maintenance_cost, current_stage, status,
                       confidence_score, time_to_payout, created_at, updated_at
                FROM income_mechanisms
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def mechanism_status_counts(self) -> list[tuple[str, int]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT status, COUNT(*)
                FROM income_mechanisms
                GROUP BY status
                ORDER BY COUNT(*) DESC
                """
            ).fetchall()
        return [(str(r[0]), int(r[1])) for r in rows]

    def create_process_blueprint(
        self,
        *,
        mechanism_id: int,
        task_type: str,
        title: str,
        description: str,
        inputs_schema: str,
        output_schema: str,
        steps_json: str,
        can_be_templated: bool,
        can_be_ruled: bool,
        can_be_coded: bool,
        automation_status: str,
        estimated_token_cost: float,
        estimated_run_cost: float,
        reuse_count: int = 0,
    ) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO process_blueprints(
                    mechanism_id, task_type, title, description, inputs_schema, output_schema, steps_json,
                    can_be_templated, can_be_ruled, can_be_coded, automation_status,
                    estimated_token_cost, estimated_run_cost, reuse_count
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mechanism_id,
                    task_type,
                    title,
                    description,
                    inputs_schema,
                    output_schema,
                    steps_json,
                    int(can_be_templated),
                    int(can_be_ruled),
                    int(can_be_coded),
                    automation_status,
                    estimated_token_cost,
                    estimated_run_cost,
                    reuse_count,
                ),
            )
            return int(cur.lastrowid)

    def list_process_blueprints(self, limit: int = 100) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, mechanism_id, task_type, title, description, inputs_schema, output_schema,
                       steps_json, can_be_templated, can_be_ruled, can_be_coded, automation_status,
                       estimated_token_cost, estimated_run_cost, reuse_count, created_at, updated_at
                FROM process_blueprints
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    # ===== Automation Candidate / Asset / Token Observation =====
    def upsert_automation_candidate(
        self,
        *,
        mechanism_id: int,
        candidate_type: str,
        title: str,
        status: str,
        confidence_score: float,
        reason: str,
    ) -> int:
        valid_status = self._validate_automation_candidate_status(status)
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM automation_candidates WHERE mechanism_id=? AND candidate_type=?",
                (mechanism_id, candidate_type),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE automation_candidates
                    SET title=?, status=?, confidence_score=?, reason=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (title, valid_status, confidence_score, reason, int(existing[0])),
                )
                return int(existing[0])
            cur = conn.execute(
                """
                INSERT INTO automation_candidates(mechanism_id, candidate_type, title, status, confidence_score, reason)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (mechanism_id, candidate_type, title, valid_status, confidence_score, reason),
            )
            return int(cur.lastrowid)

    def update_automation_candidate_status(self, candidate_id: int, status: str) -> bool:
        valid_status = self._validate_automation_candidate_status(status)
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE automation_candidates SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (valid_status, candidate_id),
            )
        return cur.rowcount > 0

    def list_automation_candidates(self, limit: int = 100) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, mechanism_id, candidate_type, title, status, confidence_score, reason, created_at, updated_at
                FROM automation_candidates
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def record_candidate_asset(self, *, candidate_id: int, asset_key: str, asset_kind: str, payload: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO candidate_assets(candidate_id, asset_key, asset_kind, payload)
                VALUES (?, ?, ?, ?)
                """,
                (candidate_id, asset_key, asset_kind, payload),
            )
            return int(cur.lastrowid)

    def list_candidate_assets(self, candidate_id: int, limit: int = 100) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, candidate_id, asset_key, asset_kind, payload, created_at
                FROM candidate_assets
                WHERE candidate_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (candidate_id, safe_limit),
            ).fetchall()

    def record_token_observation(self, *, candidate_id: int, tokens_in: int, tokens_out: int, cost_usd: float) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO token_observations(candidate_id, tokens_in, tokens_out, cost_usd)
                VALUES (?, ?, ?, ?)
                """,
                (candidate_id, tokens_in, tokens_out, cost_usd),
            )
            return int(cur.lastrowid)

    def list_token_observations(self, candidate_id: int, limit: int = 100) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, candidate_id, tokens_in, tokens_out, cost_usd, observed_at
                FROM token_observations
                WHERE candidate_id=?
                ORDER BY id DESC
                LIMIT ?
                """,
                (candidate_id, safe_limit),
            ).fetchall()

    def token_observation_summary(self) -> dict[str, float]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(tokens_in), 0), COALESCE(SUM(tokens_out), 0), COALESCE(SUM(cost_usd), 0)
                FROM token_observations
                """
            ).fetchone()
        return {
            "observation_count": int(row[0]) if row else 0,
            "tokens_in": int(row[1]) if row else 0,
            "tokens_out": int(row[2]) if row else 0,
            "token_cost_usd": float(row[3]) if row else 0.0,
        }

    # ===== Token Economy Policy / Execution Routing =====
    def upsert_token_policy(
        self,
        *,
        task_type: str,
        max_token_budget: int,
        preferred_execution_mode: str,
        allow_llm_direct: bool,
        escalation_condition: str,
        fallback_mode: str,
        caching_enabled: bool,
        mechanism_type: str = "",
        mechanism_id: int | None = None,
    ) -> int:
        preferred = self._validate_execution_mode(preferred_execution_mode)
        fallback = self._validate_execution_mode(fallback_mode)
        with self._connect() as conn:
            existing = conn.execute(
                """
                SELECT id FROM token_policies
                WHERE task_type=? AND COALESCE(mechanism_type,'')=? AND COALESCE(mechanism_id,0)=?
                """,
                (task_type, mechanism_type, mechanism_id or 0),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE token_policies
                    SET max_token_budget=?, preferred_execution_mode=?, allow_llm_direct=?, escalation_condition=?,
                        fallback_mode=?, caching_enabled=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (
                        max_token_budget,
                        preferred,
                        int(allow_llm_direct),
                        escalation_condition,
                        fallback,
                        int(caching_enabled),
                        int(existing[0]),
                    ),
                )
                return int(existing[0])
            cur = conn.execute(
                """
                INSERT INTO token_policies(
                    task_type, mechanism_type, mechanism_id, max_token_budget, preferred_execution_mode,
                    allow_llm_direct, escalation_condition, fallback_mode, caching_enabled
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_type,
                    mechanism_type,
                    mechanism_id,
                    max_token_budget,
                    preferred,
                    int(allow_llm_direct),
                    escalation_condition,
                    fallback,
                    int(caching_enabled),
                ),
            )
            return int(cur.lastrowid)

    def list_token_policies(self, limit: int = 100) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, task_type, mechanism_type, mechanism_id, max_token_budget,
                       preferred_execution_mode, allow_llm_direct, escalation_condition,
                       fallback_mode, caching_enabled, created_at, updated_at
                FROM token_policies
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def resolve_token_policy(self, *, task_type: str, mechanism_type: str = "", mechanism_id: int | None = None) -> tuple | None:
        with self._connect() as conn:
            if mechanism_id is not None:
                row = conn.execute(
                    """
                    SELECT id, task_type, mechanism_type, mechanism_id, max_token_budget,
                           preferred_execution_mode, allow_llm_direct, escalation_condition,
                           fallback_mode, caching_enabled
                    FROM token_policies
                    WHERE task_type=? AND mechanism_id=?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (task_type, mechanism_id),
                ).fetchone()
                if row:
                    return row
            if mechanism_type:
                row = conn.execute(
                    """
                    SELECT id, task_type, mechanism_type, mechanism_id, max_token_budget,
                           preferred_execution_mode, allow_llm_direct, escalation_condition,
                           fallback_mode, caching_enabled
                    FROM token_policies
                    WHERE task_type=? AND mechanism_type=?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (task_type, mechanism_type),
                ).fetchone()
                if row:
                    return row
            return conn.execute(
                """
                SELECT id, task_type, mechanism_type, mechanism_id, max_token_budget,
                       preferred_execution_mode, allow_llm_direct, escalation_condition,
                       fallback_mode, caching_enabled
                FROM token_policies
                WHERE task_type=? AND (mechanism_type='' OR mechanism_type IS NULL) AND mechanism_id IS NULL
                ORDER BY id DESC LIMIT 1
                """,
                (task_type,),
            ).fetchone()

    def has_blueprint_for_mechanism_type(self, mechanism_type: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM process_blueprints p
                JOIN income_mechanisms m ON p.mechanism_id = m.id
                WHERE m.type=?
                """,
                (mechanism_type,),
            ).fetchone()
        return bool(row and int(row[0]) > 0)

    def mechanism_asset_kinds(self, mechanism_type: str) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT a.asset_kind
                FROM candidate_assets a
                JOIN automation_candidates c ON c.id = a.candidate_id
                JOIN income_mechanisms m ON m.id = c.mechanism_id
                WHERE m.type=?
                """,
                (mechanism_type,),
            ).fetchall()
        return [str(r[0]) for r in rows]

    def get_cached_execution(self, cache_key: str) -> tuple | None:
        with self._connect() as conn:
            return conn.execute(
                "SELECT id, cache_key, task_type, execution_mode, input_hash, output, created_at FROM execution_cache WHERE cache_key=?",
                (cache_key,),
            ).fetchone()

    def put_cached_execution(self, *, cache_key: str, task_type: str, execution_mode: str, input_hash: str, output: str) -> None:
        mode = self._validate_execution_mode(execution_mode)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO execution_cache(cache_key, task_type, execution_mode, input_hash, output)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET output=excluded.output
                """,
                (cache_key, task_type, mode, input_hash, output),
            )

    def record_execution_route(
        self,
        *,
        task_id: int,
        task_type: str,
        mechanism_type: str,
        mechanism_id: int | None,
        selected_mode: str,
        fallback_mode: str,
        selected_reason: str,
        estimated_token_cost: int,
        estimated_token_savings: int,
        escalated: bool,
        status: str,
    ) -> int:
        mode = self._validate_execution_mode(selected_mode)
        fallback = self._validate_execution_mode(fallback_mode)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO execution_route_logs(
                    task_id, task_type, mechanism_type, mechanism_id, selected_mode, fallback_mode,
                    selected_reason, estimated_token_cost, estimated_token_savings, escalated, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    task_type,
                    mechanism_type,
                    mechanism_id,
                    mode,
                    fallback,
                    selected_reason,
                    estimated_token_cost,
                    estimated_token_savings,
                    int(escalated),
                    status,
                ),
            )
            return int(cur.lastrowid)

    def recent_execution_routes(self, limit: int = 50) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, task_id, task_type, mechanism_type, selected_mode, fallback_mode,
                       selected_reason, estimated_token_cost, estimated_token_savings, escalated, status, created_at
                FROM execution_route_logs
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def execution_mode_usage(self) -> list[tuple[str, int]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT selected_mode, COUNT(*) FROM execution_route_logs GROUP BY selected_mode ORDER BY COUNT(*) DESC"
            ).fetchall()
        return [(str(r[0]), int(r[1])) for r in rows]

    def execution_savings_summary(self) -> dict[str, float]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN selected_mode!='llm_direct' THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(estimated_token_savings), 0),
                    COALESCE(SUM(CASE WHEN escalated=1 THEN 1 ELSE 0 END), 0)
                FROM execution_route_logs
                """
            ).fetchone()
        return {
            "replaced_llm_count": int(row[0]) if row else 0,
            "estimated_token_savings": int(row[1]) if row else 0,
            "escalation_count": int(row[2]) if row else 0,
        }

    # ===== Existing Metrics/API Helpers =====
    def summary_metrics(self) -> dict[str, float]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(realized_revenue), 0),
                    COALESCE(SUM(estimated_cost), 0),
                    COUNT(*),
                    COALESCE(SUM(CASE WHEN status='done' THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END), 0)
                FROM task_runs
                """
            ).fetchone()
            pending_orders = conn.execute(
                """
                SELECT COUNT(*)
                FROM order_intents
                WHERE status IN ('submitted', 'partial_fill')
                """
            ).fetchone()
            hypothesis_counts = conn.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN status='validated' THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN status='rejected' THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN status='archived' THEN 1 ELSE 0 END), 0)
                FROM hypotheses
                """
            ).fetchone()
            mechanism_count = conn.execute("SELECT COUNT(*) FROM income_mechanisms").fetchone()
            blueprint_count = conn.execute("SELECT COUNT(*) FROM process_blueprints").fetchone()
            automation_candidate_count = conn.execute("SELECT COUNT(*) FROM automation_candidates").fetchone()
            execution_savings = self.execution_savings_summary()

        revenue = float(row[0]) if row else 0.0
        cost = float(row[1]) if row else 0.0
        return {
            "revenue": revenue,
            "cost": cost,
            "profit": revenue - cost,
            "task_runs": int(row[2]) if row else 0,
            "done_tasks": int(row[3]) if row else 0,
            "failed_tasks": int(row[4]) if row else 0,
            "pending_orders": int(pending_orders[0]) if pending_orders else 0,
            "validated_hypotheses": int(hypothesis_counts[0]) if hypothesis_counts else 0,
            "rejected_hypotheses": int(hypothesis_counts[1]) if hypothesis_counts else 0,
            "archived_hypotheses": int(hypothesis_counts[2]) if hypothesis_counts else 0,
            "mechanism_count": int(mechanism_count[0]) if mechanism_count else 0,
            "blueprint_count": int(blueprint_count[0]) if blueprint_count else 0,
            "automation_candidate_count": int(automation_candidate_count[0]) if automation_candidate_count else 0,
            "replaced_llm_count": int(execution_savings.get("replaced_llm_count", 0)),
            "estimated_token_savings": int(execution_savings.get("estimated_token_savings", 0)),
            "escalation_count": int(execution_savings.get("escalation_count", 0)),
        }

    def list_task_runs(self, limit: int = 100) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, task_id, assignee, channel, instrument, estimated_cost, realized_revenue, status, created_at
                FROM task_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def list_positions(self, limit: int = 100) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, market, symbol, budget, side, status, metadata, created_at
                FROM positions
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def list_order_intents(self, limit: int = 100) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, task_id, market, symbol, side, budget, client_order_id, status, created_at
                FROM order_intents
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def list_order_executions(self, limit: int = 100) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, client_order_id, broker, order_id, status, raw_response, created_at
                FROM order_executions
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def list_team_kpi_snapshots(self, limit: int = 100) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, assignee, task_count, revenue, cost, profit, created_at
                FROM team_kpi_snapshots
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def update_position_status(self, position_id: int, status: str) -> bool:
        valid_status = self._validate_position_status(status)
        with self._connect() as conn:
            cur = conn.execute("UPDATE positions SET status=? WHERE id=?", (valid_status, position_id))
        return cur.rowcount > 0

    def recent_events(self, limit: int = 20) -> Iterable[tuple[int, str, str, str]]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, event_type, details, created_at FROM system_events ORDER BY id DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        return rows
