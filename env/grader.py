"""
Grader for the SQL Query Debugger environment.

Executes agent-submitted queries against an in-memory SQLite database
and scores them 0.0–1.0 based on:
  - Does it execute without error?
  - Does it return the correct rows/values?
  - Are destructive operations absent?
  - Efficiency hints (bonus)
  - Attempt penalty
"""
from __future__ import annotations

import re
import sqlite3
import math
from typing import Any, Dict, List, Optional, Tuple

from env.models import Reward
from tasks.task_configs import TaskConfig


# Destructive SQL patterns
DESTRUCTIVE_PATTERNS = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|TRUNCATE|ALTER|CREATE|REPLACE)\b",
    re.IGNORECASE,
)

# Efficiency anti-patterns (rough heuristics)
EFFICIENCY_ANTI_PATTERNS = [
    re.compile(r"SELECT\s+\*", re.IGNORECASE),  # SELECT *
    re.compile(r"NOT\s+IN\s*\(", re.IGNORECASE),  # NOT IN subquery
]


def _build_db(task: TaskConfig) -> sqlite3.Connection:
    """Create an in-memory SQLite DB, apply schema and seed data."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(task.schema_ddl)
    for stmt in task.seed_data_sql:
        conn.execute(stmt)
    conn.commit()
    return conn


def _run_query(conn: sqlite3.Connection, query: str) -> Tuple[bool, Optional[List[Dict]], Optional[str]]:
    """Run a query. Returns (success, rows, error_message)."""
    try:
        cursor = conn.execute(query)
        rows = [dict(row) for row in cursor.fetchall()]
        return True, rows, None
    except Exception as e:
        return False, None, str(e)


def _normalize_value(v: Any) -> Any:
    """Normalize floats for comparison."""
    if isinstance(v, float):
        return round(v, 4)
    return v


def _rows_match(actual: List[Dict], expected: List[Dict], ordered: bool = True) -> float:
    """
    Compare actual vs expected rows.
    Returns score 0.0–1.0.
    For ordered results: positional match.
    For unordered: set-based match by row content.
    """
    if not expected:
        return 1.0 if not actual else 0.0

    if len(actual) != len(expected):
        # Partial credit for getting the right number of columns but wrong row count
        if actual and expected:
            # Check if column names match at least
            actual_cols = set(actual[0].keys())
            expected_cols = set(expected[0].keys())
            if actual_cols == expected_cols:
                return 0.3  # right schema, wrong rows
        return 0.0

    if ordered:
        matches = 0
        for a_row, e_row in zip(actual, expected):
            row_match = True
            for key in e_row:
                if key not in a_row:
                    row_match = False
                    break
                a_val = _normalize_value(a_row[key])
                e_val = _normalize_value(e_row[key])
                # Float tolerance
                if isinstance(e_val, float) and isinstance(a_val, (int, float)):
                    if not math.isclose(float(a_val), e_val, rel_tol=1e-3, abs_tol=1e-6):
                        row_match = False
                        break
                elif str(a_val).strip().lower() != str(e_val).strip().lower():
                    row_match = False
                    break
            if row_match:
                matches += 1
        return matches / len(expected)
    else:
        # Unordered: match by normalized row set
        actual_set = [
            tuple(sorted((k, _normalize_value(v)) for k, v in row.items()))
            for row in actual
        ]
        expected_set = [
            tuple(sorted((k, _normalize_value(v)) for k, v in row.items()))
            for row in expected
        ]
        matches = sum(1 for e in expected_set if e in actual_set)
        return matches / len(expected_set)


def _has_destructive_ops(query: str) -> bool:
    return bool(DESTRUCTIVE_PATTERNS.search(query))


def _efficiency_score(query: str) -> float:
    """Returns 0.2 bonus if no anti-patterns found, scaled down."""
    hits = sum(1 for p in EFFICIENCY_ANTI_PATTERNS if p.search(query))
    return max(0.0, 0.1 - hits * 0.05)


def grade(
    task: TaskConfig,
    fixed_query: str,
    attempt_number: int,
    max_attempts: int = 3,
) -> Reward:
    """
    Full grading pipeline.

    Returns a Reward with total score and breakdown.
    """
    # Safety check
    no_destructive = not _has_destructive_ops(fixed_query)
    if not no_destructive:
        return Reward(
            total=0.0,
            executes=False,
            result_correct=0.0,
            no_destructive_ops=False,
            efficiency_bonus=0.0,
            attempt_penalty=0.0,
            details={"reason": "Query contains destructive operation (DROP/DELETE/UPDATE/etc.)"},
        )

    # Build fresh DB
    conn = _build_db(task)

    # Execute
    executes, actual_rows, error = _run_query(conn, fixed_query)
    conn.close()

    if not executes:
        return Reward(
            total=0.0,
            executes=False,
            result_correct=0.0,
            no_destructive_ops=True,
            efficiency_bonus=0.0,
            attempt_penalty=0.0,
            details={"error": error},
        )

    # Score result correctness
    expected = task.expected_rows or []
    result_score = _rows_match(actual_rows, expected, ordered=True)

    # Efficiency bonus (small)
    eff_bonus = _efficiency_score(fixed_query) if result_score > 0 else 0.0

    # Attempt penalty: lose 0.1 per extra attempt
    attempt_penalty = max(0.0, (attempt_number - 1) * 0.1)

    # Compute total
    # Base: 80% result correctness + 20% for executing
    execution_score = 0.2  # just for running
    total = (result_score * 0.8 + execution_score) + eff_bonus - attempt_penalty
    total = round(min(1.0, max(0.0, total)), 4)

    return Reward(
        total=total,
        executes=True,
        result_correct=round(result_score, 4),
        no_destructive_ops=True,
        efficiency_bonus=round(eff_bonus, 4),
        attempt_penalty=round(attempt_penalty, 4),
        details={
            "actual_row_count": len(actual_rows),
            "expected_row_count": len(expected),
            "actual_rows_sample": actual_rows[:3],
        },
    )


def grade_reference(task: TaskConfig) -> Reward:
    """Grade the reference (correct) query — should always return ~1.0."""
    return grade(task, task.reference_query, attempt_number=1)
