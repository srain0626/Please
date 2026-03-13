from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

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
