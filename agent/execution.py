from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .persistence import SQLiteStore

TOKEN_COST_ESTIMATE = {
    "llm_direct": 1200,
    "prompt_template": 260,
    "rule_based": 120,
    "code_based": 60,
}


@dataclass
class ExecutionContext:
    task_id: int
    task_type: str
    mechanism_type: str
    mechanism_id: int | None
    instruction: str
    expected_value: float
    confidence: float


@dataclass
class RouteDecision:
    mode: str
    reason: str
    estimated_token_cost: int
    estimated_token_savings: int
    fallback_mode: str
    caching_enabled: bool
    escalation_condition: str


@dataclass
class ExecutionResult:
    mode: str
    output: str
    estimated_token_cost: int
    estimated_token_savings: int
    escalated: bool = False
    cache_hit: bool = False


class PromptTemplateExecutor:
    def run(self, instruction: str) -> str:
        return f"template-executed:{instruction[:80]}"


class RuleBasedExecutor:
    def run(self, instruction: str) -> str:
        normalized = instruction.replace("  ", " ").strip()
        return f"rule-executed:{normalized[:80]}"


class CodeBasedExecutor:
    def run(self, instruction: str) -> str:
        digest = hashlib.sha256(instruction.encode("utf-8")).hexdigest()[:10]
        return f"code-executed:artifact={digest}"


class LLMDirectExecutor:
    def __init__(self, browser_tool, shell_tool) -> None:
        self.browser_tool = browser_tool
        self.shell_tool = shell_tool

    def run(self, instruction: str) -> str:
        research = self.browser_tool.run(f"시장 검증: {instruction}")
        build = self.shell_tool.run("워크플로 빌드 및 실행")
        return f"llm-executed:research={research};build={build}"


class ExecutionRouter:
    def __init__(self, store: SQLiteStore, browser_tool, shell_tool) -> None:
        self.store = store
        self.executors = {
            "prompt_template": PromptTemplateExecutor(),
            "rule_based": RuleBasedExecutor(),
            "code_based": CodeBasedExecutor(),
            "llm_direct": LLMDirectExecutor(browser_tool, shell_tool),
        }

    def _baseline_cost(self) -> int:
        return TOKEN_COST_ESTIMATE["llm_direct"]

    def _resolve_policy(self, context: ExecutionContext) -> tuple:
        policy = self.store.resolve_token_policy(
            task_type=context.task_type,
            mechanism_type=context.mechanism_type,
            mechanism_id=context.mechanism_id,
        )
        if policy:
            return policy
        policy_id = self.store.upsert_token_policy(
            task_type=context.task_type,
            mechanism_type=context.mechanism_type,
            mechanism_id=context.mechanism_id,
            max_token_budget=500,
            preferred_execution_mode="rule_based",
            allow_llm_direct=False,
            escalation_condition="on_failure",
            fallback_mode="llm_direct",
            caching_enabled=True,
        )
        created = self.store.resolve_token_policy(
            task_type=context.task_type,
            mechanism_type=context.mechanism_type,
            mechanism_id=context.mechanism_id,
        )
        if not created:
            raise RuntimeError(f"failed to resolve token policy: {policy_id}")
        return created

    def _available_modes(self, context: ExecutionContext, allow_llm_direct: bool) -> set[str]:
        available = {"rule_based", "llm_direct" if allow_llm_direct else ""}
        if self.store.has_blueprint_for_mechanism_type(context.mechanism_type):
            available.add("rule_based")
            available.add("prompt_template")
        kinds = set(self.store.mechanism_asset_kinds(context.mechanism_type))
        if "prompt_template" in kinds:
            available.add("prompt_template")
        if "script" in kinds or "code" in kinds:
            available.add("code_based")
        available.discard("")
        return available

    def route(self, context: ExecutionContext) -> RouteDecision:
        policy = self._resolve_policy(context)
        max_budget = int(policy[4])
        preferred_mode = str(policy[5])
        allow_llm_direct = bool(int(policy[6]))
        escalation_condition = str(policy[7] or "on_failure")
        fallback_mode = str(policy[8] or "llm_direct")
        caching_enabled = bool(int(policy[9]))

        available = self._available_modes(context, allow_llm_direct=allow_llm_direct)
        if not available:
            available = {fallback_mode, "llm_direct"}

        # Prefer deterministic/cheap/reusable and policy preference if valid under budget.
        ranked = sorted(
            available,
            key=lambda m: (
                TOKEN_COST_ESTIMATE.get(m, 10_000),
                0 if m in {"code_based", "rule_based", "prompt_template"} else 1,
                0 if m in {"code_based", "prompt_template"} else 1,
            ),
        )

        selected = ranked[0]
        if preferred_mode in available and TOKEN_COST_ESTIMATE.get(preferred_mode, 99_999) <= max_budget:
            selected = preferred_mode

        # Protect low expected value tasks from expensive token paths.
        expected_limit = 180 if context.expected_value < 50 else max_budget
        if TOKEN_COST_ESTIMATE.get(selected, 99_999) > expected_limit:
            for mode in ranked:
                if TOKEN_COST_ESTIMATE.get(mode, 99_999) <= expected_limit:
                    selected = mode
                    break

        if selected == "llm_direct" and not allow_llm_direct:
            selected = fallback_mode if fallback_mode != "llm_direct" else "rule_based"

        selected_cost = TOKEN_COST_ESTIMATE.get(selected, self._baseline_cost())
        savings = max(0, self._baseline_cost() - selected_cost)
        reason = (
            f"cheap-first;deterministic-first;task_type={context.task_type};"
            f"preferred={preferred_mode};budget={max_budget};selected={selected}"
        )
        return RouteDecision(
            mode=selected,
            reason=reason,
            estimated_token_cost=selected_cost,
            estimated_token_savings=savings,
            fallback_mode=fallback_mode,
            caching_enabled=caching_enabled,
            escalation_condition=escalation_condition,
        )

    @staticmethod
    def _cache_hash(context: ExecutionContext, mode: str) -> tuple[str, str]:
        input_hash = hashlib.sha256(
            json.dumps(
                {
                    "task_type": context.task_type,
                    "mechanism_type": context.mechanism_type,
                    "instruction": context.instruction,
                    "mode": mode,
                },
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return f"{context.task_type}:{mode}:{input_hash}", input_hash

    def execute(self, context: ExecutionContext) -> ExecutionResult:
        decision = self.route(context)
        cache_key, input_hash = self._cache_hash(context, decision.mode)
        if decision.caching_enabled:
            cached = self.store.get_cached_execution(cache_key)
            if cached:
                output = str(cached[5])
                self.store.record_execution_route(
                    task_id=context.task_id,
                    task_type=context.task_type,
                    mechanism_type=context.mechanism_type,
                    mechanism_id=context.mechanism_id,
                    selected_mode=decision.mode,
                    fallback_mode=decision.fallback_mode,
                    selected_reason=f"cache_hit;{decision.reason}",
                    estimated_token_cost=0,
                    estimated_token_savings=decision.estimated_token_savings,
                    escalated=False,
                    status="cached",
                )
                return ExecutionResult(
                    mode=decision.mode,
                    output=output,
                    estimated_token_cost=0,
                    estimated_token_savings=decision.estimated_token_savings,
                    cache_hit=True,
                )

        selected_executor = self.executors[decision.mode]
        escalated = False
        status = "ok"
        try:
            output = selected_executor.run(context.instruction)
            used_mode = decision.mode
            est_cost = decision.estimated_token_cost
        except Exception as exc:  # noqa: BLE001
            if decision.escalation_condition == "on_failure":
                fallback = self.executors[decision.fallback_mode]
                output = fallback.run(context.instruction)
                used_mode = decision.fallback_mode
                est_cost = TOKEN_COST_ESTIMATE.get(decision.fallback_mode, self._baseline_cost())
                escalated = True
                status = f"escalated:{exc}"
            else:
                raise

        if decision.caching_enabled:
            self.store.put_cached_execution(
                cache_key=cache_key,
                task_type=context.task_type,
                execution_mode=used_mode,
                input_hash=input_hash,
                output=output,
            )

        self.store.record_execution_route(
            task_id=context.task_id,
            task_type=context.task_type,
            mechanism_type=context.mechanism_type,
            mechanism_id=context.mechanism_id,
            selected_mode=used_mode,
            fallback_mode=decision.fallback_mode,
            selected_reason=decision.reason,
            estimated_token_cost=est_cost,
            estimated_token_savings=max(0, self._baseline_cost() - est_cost),
            escalated=escalated,
            status=status,
        )
        return ExecutionResult(
            mode=used_mode,
            output=output,
            estimated_token_cost=est_cost,
            estimated_token_savings=max(0, self._baseline_cost() - est_cost),
            escalated=escalated,
        )
