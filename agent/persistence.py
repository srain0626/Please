from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .models import OpportunityType, Task


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
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO positions(market, symbol, budget, side, status, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (market.value, symbol, budget, side, status, metadata),
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
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO order_intents(task_id, market, symbol, side, budget, client_order_id, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(client_order_id) DO UPDATE SET status=excluded.status
                """,
                (task_id, market.value, symbol, side, budget, client_order_id, status),
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

    def update_order_intent_status(self, client_order_id: str, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE order_intents SET status=? WHERE client_order_id=?",
                (status, client_order_id),
            )

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

    def recent_events(self, limit: int = 20) -> Iterable[tuple[int, str, str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, event_type, details, created_at FROM system_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return rows
