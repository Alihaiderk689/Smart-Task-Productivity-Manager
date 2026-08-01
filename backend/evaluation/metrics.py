"""Turns a flat list of EvalCaseResult rows into the 8 headline metrics.
Each accuracy-style metric only averages over the cases where that
dimension applies (e.g. hallucination_detected is None, not False, for a
scenario with no verifiable factual claim) -- a metric with zero applicable
cases is reported as None ("not measured this run"), never a fabricated 0
or 100.
"""

from __future__ import annotations


def _rate_pct(flags: list[bool]) -> float | None:
    if not flags:
        return None
    return round(sum(1 for f in flags if f) / len(flags) * 100, 1)


def compute_metrics(results: list) -> dict:
    """`results` is any iterable of objects with the EvalCaseResult fields
    (works with real model instances or the runner's pre-save equivalents)."""
    results = list(results)
    total = len(results)
    passed = sum(1 for r in results if r.passed)

    tool_selection = [r.tool_selection_correct for r in results if r.tool_selection_correct is not None]
    planning = [r.planning_correct for r in results if r.planning_correct is not None]
    permission = [r.permission_correct for r in results if r.permission_correct is not None]
    hallucination = [r.hallucination_detected for r in results if r.hallucination_detected is not None]
    error_recovery = [r.error_recovered for r in results if r.error_recovered is not None]
    workflow_results = [r for r in results if r.category == "workflow"]

    avg_response_time_ms = round(sum(r.response_time_ms for r in results) / total, 1) if total else None

    return {
        "total_cases": total,
        "passed_cases": passed,
        "failed_cases": total - passed,
        "task_success_rate": _rate_pct([r.passed for r in results]),
        "tool_selection_accuracy": _rate_pct(tool_selection),
        "planning_accuracy": _rate_pct(planning),
        "permission_accuracy": _rate_pct(permission),
        # Framed as a rate of hallucinated (i.e. bad) responses, so lower is better --
        # matches "Hallucination Rate" as the user named it, unlike every other metric here.
        "hallucination_rate": _rate_pct(hallucination),
        "error_recovery_rate": _rate_pct(error_recovery),
        "avg_response_time_ms": avg_response_time_ms,
        "workflow_completion_rate": _rate_pct([r.passed for r in workflow_results]),
        "cases_by_category": _count_by_category(results),
    }


def _count_by_category(results: list) -> dict:
    counts: dict[str, dict[str, int]] = {}
    for r in results:
        bucket = counts.setdefault(r.category, {"passed": 0, "failed": 0})
        bucket["passed" if r.passed else "failed"] += 1
    return counts
