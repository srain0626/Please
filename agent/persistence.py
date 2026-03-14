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
DISTRIBUTION_TARGET_TYPES = {
    "blog_post",
    "freelance_proposal",
    "automation_offer",
    "digital_product_offer",
    "lead_list",
    "outreach_message",
}
CHANNEL_TYPES = {"blog", "email", "marketplace", "landing_page", "social", "direct_outreach"}
DISTRIBUTION_RUN_STATUSES = {"queued", "submitted", "delivered", "responded", "converted", "failed", "archived"}
CONVERSION_EVENT_TYPES = {
    "impression",
    "click",
    "reply",
    "lead_captured",
    "proposal_accepted",
    "sale",
    "rejected",
    "no_response",
}

ALLOCATION_RECOMMENDATION_TYPES = {
    "increase_allocation",
    "decrease_allocation",
    "pause_channel",
    "promote_variant",
    "retire_variant",
    "escalate_to_higher_effort",
    "switch_execution_mode",
}
ALLOCATION_RECOMMENDATION_STATUSES = {"pending", "auto_applied", "accepted", "rejected", "done"}


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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS distribution_targets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mechanism_id INTEGER,
                    blueprint_id INTEGER,
                    asset_id INTEGER,
                    target_type TEXT,
                    title TEXT,
                    summary TEXT,
                    payload_json TEXT,
                    status TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS distribution_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    channel_type TEXT,
                    name TEXT UNIQUE,
                    description TEXT,
                    config_json TEXT,
                    is_active INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS distribution_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_id INTEGER,
                    channel_id INTEGER,
                    mechanism_id INTEGER,
                    execution_mode TEXT,
                    status TEXT,
                    external_ref TEXT,
                    submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME,
                    notes TEXT
                )
                """
            )
            run_columns = {row[1] for row in conn.execute("PRAGMA table_info(distribution_runs)").fetchall()}
            if "variant_id" not in run_columns:
                conn.execute("ALTER TABLE distribution_runs ADD COLUMN variant_id INTEGER")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS conversion_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    target_id INTEGER,
                    mechanism_id INTEGER,
                    event_type TEXT,
                    value_estimate REAL,
                    metadata_json TEXT,
                    occurred_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS offer_variants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_id INTEGER,
                    variant_key TEXT,
                    title TEXT,
                    payload_patch_json TEXT,
                    status TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(target_id, variant_key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS allocation_policies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mechanism_id INTEGER,
                    channel_id INTEGER,
                    target_type TEXT,
                    execution_mode TEXT,
                    base_weight REAL,
                    min_trials INTEGER,
                    max_trials INTEGER,
                    cooldown_hours REAL,
                    is_active INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS allocation_recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mechanism_id INTEGER,
                    channel_id INTEGER,
                    target_type TEXT,
                    variant_id INTEGER,
                    recommendation_type TEXT,
                    rationale TEXT,
                    expected_impact REAL,
                    confidence REAL,
                    status TEXT,
                    auto_applied INTEGER,
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


    def _validate_distribution_target_type(self, target_type: str) -> str:
        normalized = target_type.lower().strip()
        if normalized not in DISTRIBUTION_TARGET_TYPES:
            raise ValueError(f"invalid distribution target type: {target_type}")
        return normalized

    def _validate_channel_type(self, channel_type: str) -> str:
        normalized = channel_type.lower().strip()
        if normalized not in CHANNEL_TYPES:
            raise ValueError(f"invalid channel type: {channel_type}")
        return normalized

    def _validate_distribution_run_status(self, status: str) -> str:
        normalized = status.lower().strip()
        if normalized not in DISTRIBUTION_RUN_STATUSES:
            raise ValueError(f"invalid distribution run status: {status}")
        return normalized

    def _validate_conversion_event_type(self, event_type: str) -> str:
        normalized = event_type.lower().strip()
        if normalized not in CONVERSION_EVENT_TYPES:
            raise ValueError(f"invalid conversion event type: {event_type}")
        return normalized


    def _validate_recommendation_type(self, recommendation_type: str) -> str:
        normalized = recommendation_type.lower().strip()
        if normalized not in ALLOCATION_RECOMMENDATION_TYPES:
            raise ValueError(f"invalid recommendation type: {recommendation_type}")
        return normalized

    def _validate_recommendation_status(self, status: str) -> str:
        normalized = status.lower().strip()
        if normalized not in ALLOCATION_RECOMMENDATION_STATUSES:
            raise ValueError(f"invalid recommendation status: {status}")
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

    # ===== Distribution & Conversion Loop =====
    def create_distribution_target(
        self,
        *,
        mechanism_id: int,
        target_type: str,
        title: str,
        summary: str,
        payload_json: str,
        status: str = "draft",
        blueprint_id: int | None = None,
        asset_id: int | None = None,
    ) -> int:
        valid_type = self._validate_distribution_target_type(target_type)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO distribution_targets(
                    mechanism_id, blueprint_id, asset_id, target_type, title, summary, payload_json, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (mechanism_id, blueprint_id, asset_id, valid_type, title, summary, payload_json, status),
            )
            return int(cur.lastrowid)

    def list_distribution_targets(self, limit: int = 100) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, mechanism_id, blueprint_id, asset_id, target_type, title, summary, payload_json, status, created_at, updated_at
                FROM distribution_targets
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def update_distribution_target_status(self, target_id: int, status: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE distribution_targets SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (status, target_id),
            )
        return cur.rowcount > 0

    def create_distribution_channel(
        self,
        *,
        channel_type: str,
        name: str,
        description: str,
        config_json: str,
        is_active: bool = True,
    ) -> int:
        valid_type = self._validate_channel_type(channel_type)
        with self._connect() as conn:
            existing = conn.execute("SELECT id FROM distribution_channels WHERE name=?", (name,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE distribution_channels
                    SET channel_type=?, description=?, config_json=?, is_active=?, updated_at=CURRENT_TIMESTAMP
                    WHERE id=?
                    """,
                    (valid_type, description, config_json, int(is_active), int(existing[0])),
                )
                return int(existing[0])
            cur = conn.execute(
                """
                INSERT INTO distribution_channels(channel_type, name, description, config_json, is_active)
                VALUES (?, ?, ?, ?, ?)
                """,
                (valid_type, name, description, config_json, int(is_active)),
            )
            return int(cur.lastrowid)

    def list_distribution_channels(self, limit: int = 100, active_only: bool = False) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            if active_only:
                return conn.execute(
                    """
                    SELECT id, channel_type, name, description, config_json, is_active, created_at, updated_at
                    FROM distribution_channels
                    WHERE is_active=1
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
            return conn.execute(
                """
                SELECT id, channel_type, name, description, config_json, is_active, created_at, updated_at
                FROM distribution_channels
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def create_distribution_run(
        self,
        *,
        target_id: int,
        channel_id: int,
        mechanism_id: int,
        execution_mode: str,
        status: str,
        external_ref: str,
        notes: str,
        variant_id: int | None = None,
    ) -> int:
        valid_status = self._validate_distribution_run_status(status)
        mode = self._validate_execution_mode(execution_mode)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO distribution_runs(target_id, channel_id, mechanism_id, execution_mode, status, external_ref, notes, variant_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (target_id, channel_id, mechanism_id, mode, valid_status, external_ref, notes, variant_id),
            )
            return int(cur.lastrowid)

    def update_distribution_run_status(self, run_id: int, status: str, notes: str = "") -> bool:
        valid_status = self._validate_distribution_run_status(status)
        with self._connect() as conn:
            cur = conn.execute(
                """
                UPDATE distribution_runs
                SET status=?, notes=CASE WHEN ?='' THEN notes ELSE ? END,
                    completed_at=CASE WHEN ? IN ('delivered','responded','converted','failed','archived') THEN CURRENT_TIMESTAMP ELSE completed_at END
                WHERE id=?
                """,
                (valid_status, notes, notes, valid_status, run_id),
            )
        return cur.rowcount > 0

    def list_distribution_runs(self, limit: int = 100) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, target_id, channel_id, mechanism_id, execution_mode, status, external_ref, submitted_at, completed_at, notes, variant_id
                FROM distribution_runs
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def update_distribution_run_variant(self, run_id: int, variant_id: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute("UPDATE distribution_runs SET variant_id=? WHERE id=?", (variant_id, run_id))
        return cur.rowcount > 0

    def record_conversion_event(
        self,
        *,
        run_id: int,
        target_id: int,
        mechanism_id: int,
        event_type: str,
        value_estimate: float,
        metadata_json: str,
    ) -> int:
        valid_event = self._validate_conversion_event_type(event_type)
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO conversion_events(run_id, target_id, mechanism_id, event_type, value_estimate, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (run_id, target_id, mechanism_id, valid_event, value_estimate, metadata_json),
            )
            return int(cur.lastrowid)

    def list_conversion_events(self, limit: int = 100) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, run_id, target_id, mechanism_id, event_type, value_estimate, metadata_json, occurred_at
                FROM conversion_events
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def apply_distribution_feedback(self, mechanism_id: int, confidence_delta: float, repeatability_delta: float) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT confidence_score, repeatability_score FROM income_mechanisms WHERE id=?",
                (mechanism_id,),
            ).fetchone()
            if not row:
                return False
            confidence = max(0.0, min(1.0, float(row[0]) + confidence_delta))
            repeatability = max(0.0, min(1.0, float(row[1]) + repeatability_delta))
            conn.execute(
                """
                UPDATE income_mechanisms
                SET confidence_score=?, repeatability_score=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=?
                """,
                (confidence, repeatability, mechanism_id),
            )
            return True

    def apply_feedback_event(self, event_type: str, mechanism_id: int) -> bool:
        event = self._validate_conversion_event_type(event_type)
        positive = {"proposal_accepted", "sale", "lead_captured"}
        negative = {"rejected", "no_response"}
        if event in positive:
            changed = self.apply_distribution_feedback(mechanism_id, confidence_delta=0.05, repeatability_delta=0.03)
            self._apply_hypothesis_feedback(+0.03)
            return changed
        if event in negative:
            changed = self.apply_distribution_feedback(mechanism_id, confidence_delta=-0.04, repeatability_delta=-0.03)
            self._apply_hypothesis_feedback(-0.03)
            return changed
        return True

    def _apply_hypothesis_feedback(self, delta: float) -> None:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, confidence_score
                FROM hypotheses
                WHERE status IN ('testing', 'validated')
                ORDER BY updated_at DESC
                LIMIT 5
                """
            ).fetchall()
            for hypothesis_id, confidence in rows:
                updated = max(0.0, min(1.0, float(confidence) + delta))
                conn.execute(
                    "UPDATE hypotheses SET confidence_score=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (updated, int(hypothesis_id)),
                )

    def conversion_metrics_by_channel(self) -> list[tuple]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.name,
                    COUNT(DISTINCT r.id) as submitted_count,
                    COALESCE(SUM(CASE WHEN e.event_type IN ('reply','lead_captured','proposal_accepted','sale') THEN 1 ELSE 0 END), 0) as responses,
                    COALESCE(SUM(CASE WHEN e.event_type IN ('proposal_accepted','sale') THEN 1 ELSE 0 END), 0) as conversions,
                    COALESCE(SUM(e.value_estimate), 0) as revenue_estimate
                FROM distribution_channels c
                LEFT JOIN distribution_runs r ON r.channel_id = c.id
                LEFT JOIN conversion_events e ON e.run_id = r.id
                GROUP BY c.id, c.name
                ORDER BY submitted_count DESC
                """
            ).fetchall()
        data: list[tuple] = []
        for name, submitted, responses, conversions, revenue in rows:
            submitted_i = int(submitted)
            response_rate = (float(responses) / submitted_i) if submitted_i > 0 else 0.0
            conversion_rate = (float(conversions) / submitted_i) if submitted_i > 0 else 0.0
            data.append((str(name), submitted_i, round(response_rate, 4), round(conversion_rate, 4), round(float(revenue), 2)))
        return data

    def conversion_metrics_by_mechanism(self) -> list[tuple]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT m.id, m.type, m.title,
                       COALESCE(SUM(CASE WHEN e.event_type IN ('proposal_accepted','sale') THEN 1 ELSE 0 END), 0) as conversions,
                       COALESCE(SUM(e.value_estimate), 0) as revenue
                FROM income_mechanisms m
                LEFT JOIN conversion_events e ON e.mechanism_id = m.id
                GROUP BY m.id, m.type, m.title
                ORDER BY conversions DESC, revenue DESC
                """
            ).fetchall()
        return [(int(r[0]), str(r[1]), str(r[2]), int(r[3]), round(float(r[4]), 2)) for r in rows]

    def conversion_metrics_by_target_type(self) -> list[tuple]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT t.target_type,
                       COUNT(DISTINCT r.id) as runs,
                       COALESCE(SUM(CASE WHEN e.event_type IN ('proposal_accepted','sale') THEN 1 ELSE 0 END), 0) as conversions,
                       COALESCE(SUM(e.value_estimate), 0) as revenue
                FROM distribution_targets t
                LEFT JOIN distribution_runs r ON r.target_id = t.id
                LEFT JOIN conversion_events e ON e.run_id = r.id
                GROUP BY t.target_type
                ORDER BY conversions DESC
                """
            ).fetchall()
        return [(str(r[0]), int(r[1]), int(r[2]), round(float(r[3]), 2)) for r in rows]

    def distribution_token_efficiency(self) -> dict[str, float]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN e.event_type IN ('proposal_accepted','sale') THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(e.value_estimate), 0),
                    COALESCE(SUM(r.estimated_token_cost), 0)
                FROM conversion_events e
                LEFT JOIN execution_route_logs r ON r.task_id = e.run_id
                """
            ).fetchone()
        conversions = int(row[0]) if row else 0
        revenue = float(row[1]) if row else 0.0
        tokens = float(row[2]) if row else 0.0
        return {
            "conversion_count": conversions,
            "estimated_revenue": round(revenue, 2),
            "token_spend_estimate": round(tokens, 2),
            "revenue_per_token": round(revenue / tokens, 6) if tokens > 0 else 0.0,
        }

    # ===== Channel Allocation & Offer Optimization =====
    def create_offer_variant(
        self,
        *,
        target_id: int,
        variant_key: str,
        title: str,
        payload_patch_json: str,
        status: str = "active",
    ) -> int:
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT id FROM offer_variants WHERE target_id=? AND variant_key=?",
                (target_id, variant_key),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE offer_variants
                    SET title=?, payload_patch_json=?, status=?
                    WHERE id=?
                    """,
                    (title, payload_patch_json, status, int(existing[0])),
                )
                return int(existing[0])
            cur = conn.execute(
                """
                INSERT INTO offer_variants(target_id, variant_key, title, payload_patch_json, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (target_id, variant_key, title, payload_patch_json, status),
            )
            return int(cur.lastrowid)

    def list_offer_variants(self, target_id: int | None = None, limit: int = 100) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            if target_id is not None:
                return conn.execute(
                    """
                    SELECT id, target_id, variant_key, title, payload_patch_json, status, created_at
                    FROM offer_variants
                    WHERE target_id=?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (target_id, safe_limit),
                ).fetchall()
            return conn.execute(
                """
                SELECT id, target_id, variant_key, title, payload_patch_json, status, created_at
                FROM offer_variants
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def upsert_allocation_policy(
        self,
        *,
        mechanism_id: int | None,
        channel_id: int | None,
        target_type: str | None,
        execution_mode: str | None,
        base_weight: float,
        min_trials: int,
        max_trials: int,
        cooldown_hours: float,
        is_active: bool,
    ) -> int:
        normalized_target = self._validate_distribution_target_type(target_type) if target_type else None
        normalized_mode = self._validate_execution_mode(execution_mode) if execution_mode else None
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO allocation_policies(
                    mechanism_id, channel_id, target_type, execution_mode, base_weight,
                    min_trials, max_trials, cooldown_hours, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mechanism_id,
                    channel_id,
                    normalized_target,
                    normalized_mode,
                    base_weight,
                    min_trials,
                    max_trials,
                    cooldown_hours,
                    int(is_active),
                ),
            )
            return int(cur.lastrowid)

    def list_allocation_policies(self, limit: int = 100, active_only: bool = False) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            if active_only:
                return conn.execute(
                    """
                    SELECT id, mechanism_id, channel_id, target_type, execution_mode, base_weight, min_trials,
                           max_trials, cooldown_hours, is_active, created_at, updated_at
                    FROM allocation_policies
                    WHERE is_active=1
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
            return conn.execute(
                """
                SELECT id, mechanism_id, channel_id, target_type, execution_mode, base_weight, min_trials,
                       max_trials, cooldown_hours, is_active, created_at, updated_at
                FROM allocation_policies
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def record_allocation_recommendation(
        self,
        *,
        mechanism_id: int | None,
        channel_id: int | None,
        target_type: str | None,
        variant_id: int | None,
        recommendation_type: str,
        rationale: str,
        expected_impact: float,
        confidence: float,
        status: str = "pending",
        auto_applied: bool = False,
    ) -> int:
        rec_type = self._validate_recommendation_type(recommendation_type)
        rec_status = self._validate_recommendation_status(status)
        normalized_target = self._validate_distribution_target_type(target_type) if target_type else None
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO allocation_recommendations(
                    mechanism_id, channel_id, target_type, variant_id, recommendation_type,
                    rationale, expected_impact, confidence, status, auto_applied
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mechanism_id,
                    channel_id,
                    normalized_target,
                    variant_id,
                    rec_type,
                    rationale,
                    expected_impact,
                    max(0.0, min(1.0, confidence)),
                    rec_status,
                    int(auto_applied),
                ),
            )
            return int(cur.lastrowid)

    def list_allocation_recommendations(self, limit: int = 100) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT id, mechanism_id, channel_id, target_type, variant_id, recommendation_type,
                       rationale, expected_impact, confidence, status, auto_applied, created_at
                FROM allocation_recommendations
                ORDER BY id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

    def update_allocation_recommendation_status(self, recommendation_id: int, status: str) -> bool:
        rec_status = self._validate_recommendation_status(status)
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE allocation_recommendations SET status=? WHERE id=?",
                (rec_status, recommendation_id),
            )
        return cur.rowcount > 0

    def performance_summary(
        self,
        *,
        dimension: str,
        limit: int = 100,
    ) -> list[tuple]:
        safe_limit = self._validate_limit(limit)
        mapping = {
            "mechanism": "CAST(r.mechanism_id AS TEXT)",
            "channel": "CAST(r.channel_id AS TEXT)",
            "target_type": "t.target_type",
            "execution_mode": "r.execution_mode",
            "variant": "COALESCE(CAST(r.variant_id AS TEXT), 'none')",
            "offer_title": "t.title",
        }
        group_expr = mapping.get(dimension)
        if not group_expr:
            raise ValueError(f"unsupported dimension: {dimension}")

        query = f"""
            SELECT
                {group_expr} AS dim_key,
                COUNT(DISTINCT r.id) AS submissions,
                COALESCE(SUM(CASE WHEN r.status IN ('delivered','responded','converted') THEN 1 ELSE 0 END), 0) AS deliveries,
                COALESCE(SUM(CASE WHEN e.event_type IN ('reply','lead_captured','proposal_accepted','sale') THEN 1 ELSE 0 END), 0) AS responses,
                COALESCE(SUM(CASE WHEN e.event_type IN ('proposal_accepted','sale') THEN 1 ELSE 0 END), 0) AS conversions,
                COALESCE(SUM(e.value_estimate), 0) AS estimated_revenue,
                COALESCE(SUM(CASE WHEN e.event_type='rejected' OR r.status='failed' THEN 1 ELSE 0 END), 0) AS failures,
                COALESCE(SUM(CASE WHEN e.event_type='no_response' THEN 1 ELSE 0 END), 0) AS no_responses,
                COALESCE(AVG(el.estimated_token_cost), 0) AS token_cost,
                COALESCE(AVG(m.expected_cost), 0) AS execution_cost,
                COALESCE(AVG(m.repeatability_score), 0) AS repeatability_score,
                COALESCE(AVG(m.automation_potential), 0) AS automation_potential
            FROM distribution_runs r
            LEFT JOIN distribution_targets t ON t.id = r.target_id
            LEFT JOIN conversion_events e ON e.run_id = r.id
            LEFT JOIN execution_route_logs el ON el.task_id = r.id
            LEFT JOIN income_mechanisms m ON m.id = r.mechanism_id
            GROUP BY dim_key
            ORDER BY submissions DESC
            LIMIT ?
        """

        with self._connect() as conn:
            rows = conn.execute(query, (safe_limit,)).fetchall()

        results: list[tuple] = []
        for row in rows:
            key = str(row[0])
            submissions = int(row[1])
            deliveries = int(row[2])
            responses = int(row[3])
            conversions = int(row[4])
            revenue = float(row[5])
            failures = int(row[6])
            no_responses = int(row[7])
            token_cost = float(row[8])
            execution_cost = float(row[9])
            repeatability = float(row[10])
            automation = float(row[11])

            response_rate = responses / submissions if submissions else 0.0
            conversion_rate = conversions / submissions if submissions else 0.0
            revenue_per_run = revenue / submissions if submissions else 0.0
            revenue_per_token = revenue / token_cost if token_cost > 0 else 0.0
            conversion_per_token = conversions / token_cost if token_cost > 0 else 0.0
            failure_rate = failures / submissions if submissions else 0.0
            no_response_rate = no_responses / submissions if submissions else 0.0

            results.append(
                (
                    key,
                    submissions,
                    deliveries,
                    responses,
                    conversions,
                    round(revenue, 4),
                    round(response_rate, 6),
                    round(conversion_rate, 6),
                    round(revenue_per_run, 6),
                    round(revenue_per_token, 6),
                    round(conversion_per_token, 6),
                    round(failure_rate, 6),
                    round(no_response_rate, 6),
                    round(repeatability, 6),
                    round(automation, 6),
                    round(execution_cost, 6),
                    round(token_cost, 6),
                )
            )
        return results

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
            distribution_target_count = conn.execute("SELECT COUNT(*) FROM distribution_targets").fetchone()
            distribution_channel_count = conn.execute("SELECT COUNT(*) FROM distribution_channels").fetchone()
            distribution_run_count = conn.execute("SELECT COUNT(*) FROM distribution_runs").fetchone()
            conversion_event_count = conn.execute("SELECT COUNT(*) FROM conversion_events").fetchone()
            allocation_policy_count = conn.execute("SELECT COUNT(*) FROM allocation_policies").fetchone()
            offer_variant_count = conn.execute("SELECT COUNT(*) FROM offer_variants").fetchone()
            allocation_recommendation_count = conn.execute("SELECT COUNT(*) FROM allocation_recommendations").fetchone()
            auto_applied_recommendation_count = conn.execute("SELECT COUNT(*) FROM allocation_recommendations WHERE auto_applied=1").fetchone()
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
            "distribution_target_count": int(distribution_target_count[0]) if distribution_target_count else 0,
            "distribution_channel_count": int(distribution_channel_count[0]) if distribution_channel_count else 0,
            "distribution_run_count": int(distribution_run_count[0]) if distribution_run_count else 0,
            "conversion_event_count": int(conversion_event_count[0]) if conversion_event_count else 0,
            "allocation_policy_count": int(allocation_policy_count[0]) if allocation_policy_count else 0,
            "offer_variant_count": int(offer_variant_count[0]) if offer_variant_count else 0,
            "allocation_recommendation_count": int(allocation_recommendation_count[0]) if allocation_recommendation_count else 0,
            "auto_applied_recommendation_count": int(auto_applied_recommendation_count[0]) if auto_applied_recommendation_count else 0,
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
