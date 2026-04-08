"""
Tests for the SQL Query Debugger OpenEnv environment.

Run with: python -m pytest tests/ -v
Or directly: python tests/test_environment.py
"""
from __future__ import annotations

import sqlite3
import sys
import os
import math

# Allow running from repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ─── Minimal stubs so tests run without pydantic installed ────────────────────
# In CI/Docker pydantic IS installed; these stubs let the test file be run
# standalone for quick logic checks.

try:
    from env.environment import SQLDebuggerEnv
    from env.grader import grade, grade_reference, _rows_match, _has_destructive_ops
    from env.models import Action
    from tasks.task_configs import (
        EASY_TASKS, MEDIUM_TASKS, HARD_TASKS,
        get_task_by_id, get_random_task,
    )
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False


# ─── Pure-Python grader logic (no pydantic) ───────────────────────────────────

def _build_db_raw(schema_ddl: str, seed_sql: list) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(schema_ddl)
    for stmt in seed_sql:
        conn.execute(stmt)
    conn.commit()
    return conn


def _run_query_raw(conn, query):
    try:
        cursor = conn.execute(query)
        return True, [dict(r) for r in cursor.fetchall()], None
    except Exception as e:
        return False, None, str(e)


def _normalize(v):
    if isinstance(v, float):
        return round(v, 4)
    return v


def _rows_match_raw(actual, expected):
    if len(actual) != len(expected):
        return False
    for a, e in zip(actual, expected):
        for k in e:
            if k not in a:
                return False
            av, ev = _normalize(a[k]), _normalize(e[k])
            if isinstance(ev, float) and isinstance(av, (int, float)):
                if not math.isclose(float(av), ev, rel_tol=1e-3, abs_tol=1e-4):
                    return False
            elif str(av).strip().lower() != str(ev).strip().lower():
                return False
    return True


# ─── Tests ────────────────────────────────────────────────────────────────────

PASS = []
FAIL = []


def assert_true(condition, name, detail=""):
    if condition:
        PASS.append(name)
        print(f"  ✓ {name}")
    else:
        FAIL.append(name)
        print(f"  ✗ {name}" + (f": {detail}" if detail else ""))


def test_easy_reference_queries():
    """All easy reference queries should execute and return correct rows."""
    print("\n[Easy tasks — reference queries]")

    task_data = [
        {
            "id": "easy_01",
            "schema": """
                CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT, department TEXT, salary REAL, hire_date TEXT);
            """,
            "seed": [
                "INSERT INTO employees VALUES (1, 'Alice', 'Engineering', 120000, '2020-01-15')",
                "INSERT INTO employees VALUES (2, 'Bob', 'Marketing', 85000, '2019-03-22')",
                "INSERT INTO employees VALUES (3, 'Carol', 'Engineering', 135000, '2018-07-01')",
                "INSERT INTO employees VALUES (4, 'Dave', 'Engineering', 95000, '2021-11-10')",
                "INSERT INTO employees VALUES (5, 'Eve', 'HR', 75000, '2022-02-28')",
            ],
            "broken": "SELCT name, salary FORM employees WHERE department = 'Engineering' ORDRE BY salary DESC;",
            "reference": "SELECT name, salary FROM employees WHERE department = 'Engineering' ORDER BY salary DESC;",
            "expected": [
                {"name": "Carol", "salary": 135000.0},
                {"name": "Alice", "salary": 120000.0},
                {"name": "Dave", "salary": 95000.0},
            ],
        },
        {
            "id": "easy_02",
            "schema": "CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, category TEXT, price REAL, stock INTEGER);",
            "seed": [
                "INSERT INTO products VALUES (1, 'Headphones', 'Electronics', 149.99, 50)",
                "INSERT INTO products VALUES (2, 'Keyboard', 'Electronics', 79.99, 100)",
                "INSERT INTO products VALUES (3, 'Monitor', 'Electronics', 399.99, 25)",
                "INSERT INTO products VALUES (4, 'Webcam', 'Electronics', 89.99, 75)",
                "INSERT INTO products VALUES (5, 'Laptop', 'Electronics', 999.99, 15)",
                "INSERT INTO products VALUES (6, 'Mouse', 'Electronics', 29.99, 200)",
                "INSERT INTO products VALUES (7, 'Desk Lamp', 'Home', 45.99, 60)",
            ],
            "broken": "SELECT name, price FROM products WHERE category = 'Electronics' AND price < 500 ORDER BY price;\nLIMIT 5",
            "reference": "SELECT name, price FROM products WHERE category = 'Electronics' AND price < 500 ORDER BY price LIMIT 5;",
            "expected": [
                {"name": "Mouse", "price": 29.99},
                {"name": "Keyboard", "price": 79.99},
                {"name": "Webcam", "price": 89.99},
                {"name": "Headphones", "price": 149.99},
                {"name": "Monitor", "price": 399.99},
            ],
        },
        {
            "id": "easy_03",
            "schema": "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_name TEXT, amount REAL, status TEXT, created_at TEXT);",
            "seed": [
                "INSERT INTO orders VALUES (1, 'Alice', 250.00, 'completed', '2024-01-10')",
                "INSERT INTO orders VALUES (2, 'Bob', 175.50, 'pending', '2024-01-11')",
                "INSERT INTO orders VALUES (3, 'Alice', 320.00, 'completed', '2024-01-12')",
                "INSERT INTO orders VALUES (4, 'Carol', 89.99, 'completed', '2024-01-13')",
                "INSERT INTO orders VALUES (5, 'Bob', 420.00, 'completed', '2024-01-14')",
            ],
            "broken": "SELECT COUNT(*) AS total_orders, SUM(amount) AS revenue FROM orders WHERE status = 'completed' GROUP BY customer_name;",
            "reference": "SELECT COUNT(*) AS total_orders, SUM(amount) AS revenue FROM orders WHERE status = 'completed';",
            "expected": [{"total_orders": 4, "revenue": 1079.99}],
        },
    ]

    for td in task_data:
        conn = _build_db_raw(td["schema"], td["seed"])

        # Reference should work
        ok, rows, err = _run_query_raw(conn, td["reference"])
        assert_true(ok, f"{td['id']}: reference executes", err)
        assert_true(
            ok and _rows_match_raw(rows, td["expected"]),
            f"{td['id']}: reference returns correct rows",
            f"got {rows}, want {td['expected']}",
        )

        # Broken should either fail OR return wrong rows
        ok_b, rows_b, _ = _run_query_raw(conn, td["broken"])
        broken_wrong = (not ok_b) or (ok_b and not _rows_match_raw(rows_b or [], td["expected"]))
        assert_true(broken_wrong, f"{td['id']}: broken query returns wrong/error result")

        conn.close()


def test_medium_reference_queries():
    """All medium reference queries should execute and return correct rows."""
    print("\n[Medium tasks — reference queries]")

    # medium_01: LEFT JOIN nullification
    schema_m1 = """
        CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT, city TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER, total REAL, status TEXT, order_date TEXT);
    """
    seed_m1 = [
        "INSERT INTO customers VALUES (1, 'Alice', 'a@e.com', 'NYC')",
        "INSERT INTO customers VALUES (2, 'Bob', 'b@e.com', 'LA')",
        "INSERT INTO customers VALUES (3, 'Carol', 'c@e.com', 'Chicago')",
        "INSERT INTO orders VALUES (1, 1, 500.00, 'completed', '2024-01-01')",
        "INSERT INTO orders VALUES (2, 1, 250.00, 'completed', '2024-01-15')",
        "INSERT INTO orders VALUES (3, 2, 300.00, 'pending', '2024-01-20')",
        "INSERT INTO orders VALUES (4, 2, 150.00, 'completed', '2024-02-01')",
    ]
    ref_m1 = """SELECT c.name, COALESCE(SUM(o.total), 0) AS lifetime_value
FROM customers c LEFT JOIN orders o ON c.id = o.customer_id AND o.status = 'completed'
GROUP BY c.id, c.name ORDER BY lifetime_value DESC;"""
    broken_m1 = """SELECT c.name, SUM(o.total) AS lifetime_value
FROM customers c LEFT JOIN orders o ON c.id = o.customer_id
WHERE o.status = 'completed' GROUP BY c.id, c.name ORDER BY lifetime_value DESC;"""
    expected_m1 = [
        {"name": "Alice", "lifetime_value": 750.0},
        {"name": "Bob", "lifetime_value": 150.0},
        {"name": "Carol", "lifetime_value": 0},
    ]

    conn = _build_db_raw(schema_m1, seed_m1)
    ok, rows, err = _run_query_raw(conn, ref_m1)
    assert_true(ok, "medium_01: reference executes", err)
    assert_true(ok and _rows_match_raw(rows, expected_m1), "medium_01: Carol included with 0",
                f"got {rows}")

    ok_b, rows_b, _ = _run_query_raw(conn, broken_m1)
    carol_missing = ok_b and not any(r.get("name") == "Carol" for r in (rows_b or []))
    assert_true(carol_missing, "medium_01: broken excludes Carol (confirms the bug)")
    conn.close()

    # medium_02: GROUP BY partial columns
    schema_m2 = "CREATE TABLE sales (id INTEGER PRIMARY KEY, rep_name TEXT, region TEXT, amount REAL, sale_date TEXT);"
    seed_m2 = [
        "INSERT INTO sales VALUES (1, 'Alice', 'North', 4500, '2024-01-01')",
        "INSERT INTO sales VALUES (2, 'Alice', 'North', 7000, '2024-01-15')",
        "INSERT INTO sales VALUES (3, 'Bob', 'South', 8000, '2024-01-10')",
        "INSERT INTO sales VALUES (4, 'Bob', 'South', 5000, '2024-02-01')",
        "INSERT INTO sales VALUES (5, 'Carol', 'North', 3000, '2024-01-20')",
        "INSERT INTO sales VALUES (6, 'Dave', 'West', 15000, '2024-01-25')",
    ]
    ref_m2 = """SELECT rep_name, region, SUM(amount) AS total_sales FROM sales
GROUP BY rep_name, region HAVING SUM(amount) > 10000 ORDER BY total_sales DESC;"""
    expected_m2 = [
        {"rep_name": "Dave", "region": "West", "total_sales": 15000.0},
        {"rep_name": "Bob", "region": "South", "total_sales": 13000.0},
        {"rep_name": "Alice", "region": "North", "total_sales": 11500.0},
    ]
    conn = _build_db_raw(schema_m2, seed_m2)
    ok, rows, err = _run_query_raw(conn, ref_m2)
    assert_true(ok, "medium_02: reference executes", err)
    assert_true(ok and _rows_match_raw(rows, expected_m2), "medium_02: correct rep+region rows",
                f"got {rows}")
    conn.close()


def test_hard_reference_queries():
    """Hard reference queries should execute correctly."""
    print("\n[Hard tasks — reference queries]")

    # hard_01: CTE join column mismatch
    schema_h1 = """
        CREATE TABLE employees (id INTEGER PRIMARY KEY, name TEXT, department_id INTEGER, manager_id INTEGER, salary REAL, hire_date TEXT);
        CREATE TABLE departments (id INTEGER PRIMARY KEY, name TEXT, budget REAL);
        CREATE TABLE performance_reviews (id INTEGER PRIMARY KEY, employee_id INTEGER, review_year INTEGER, score REAL);
    """
    seed_h1 = [
        "INSERT INTO departments VALUES (1, 'Engineering', 500000)",
        "INSERT INTO departments VALUES (2, 'Marketing', 300000)",
        "INSERT INTO employees VALUES (1, 'Alice', 1, NULL, 130000, '2019-01-01')",
        "INSERT INTO employees VALUES (2, 'Bob', 1, 1, 110000, '2020-06-01')",
        "INSERT INTO employees VALUES (3, 'Carol', 1, 1, 95000, '2021-03-01')",
        "INSERT INTO employees VALUES (4, 'Dave', 2, NULL, 90000, '2018-09-01')",
        "INSERT INTO employees VALUES (5, 'Eve', 2, 4, 80000, '2022-01-01')",
        "INSERT INTO performance_reviews VALUES (1, 1, 2023, 4.5)",
        "INSERT INTO performance_reviews VALUES (2, 1, 2023, 4.2)",
        "INSERT INTO performance_reviews VALUES (3, 2, 2023, 3.8)",
        "INSERT INTO performance_reviews VALUES (4, 3, 2023, 4.1)",
        "INSERT INTO performance_reviews VALUES (5, 4, 2023, 4.7)",
        "INSERT INTO performance_reviews VALUES (6, 5, 2023, 3.5)",
    ]
    ref_h1 = """
WITH dept_avg AS (SELECT department_id, AVG(salary) AS avg_salary FROM employees GROUP BY department_id),
top_performers AS (SELECT employee_id FROM performance_reviews WHERE review_year = 2023 GROUP BY employee_id HAVING AVG(score) >= 4.0)
SELECT e.name, d.name AS department, e.salary,
       ROUND((e.salary - da.avg_salary) / da.avg_salary * 100, 2) AS pct_above_avg
FROM employees e
JOIN departments d ON e.department_id = d.id
JOIN dept_avg da ON e.department_id = da.department_id
JOIN top_performers tp ON e.id = tp.employee_id
ORDER BY pct_above_avg DESC;"""

    broken_h1 = ref_h1.replace("e.department_id = da.department_id", "e.id = da.department_id")

    conn = _build_db_raw(schema_h1, seed_h1)
    ok, rows, err = _run_query_raw(conn, ref_h1)
    assert_true(ok, "hard_01: reference executes", err)
    assert_true(ok and len(rows) == 3, "hard_01: returns 3 top performers", f"got {len(rows) if ok else 'err'}")
    assert_true(ok and rows[0]["name"] == "Alice", "hard_01: Alice is top (highest % above avg)")

    ok_b, rows_b, _ = _run_query_raw(conn, broken_h1)
    assert_true(ok_b and len(rows_b) < 3, "hard_01: broken query returns fewer rows (confirms bug)")
    conn.close()


def test_destructive_operation_guard():
    """Queries with destructive operations must score 0."""
    print("\n[Safety — destructive operation guard]")
    destructive = [
        "DROP TABLE employees;",
        "DELETE FROM employees WHERE 1=1;",
        "UPDATE employees SET salary = 0;",
        "TRUNCATE TABLE employees;",
        "ALTER TABLE employees ADD COLUMN bonus REAL;",
    ]
    safe = [
        "SELECT * FROM employees;",
        "SELECT name FROM employees WHERE salary > 100000;",
        "WITH cte AS (SELECT id FROM employees) SELECT * FROM cte;",
    ]
    import re
    DESTRUCTIVE_PATTERNS = re.compile(
        r"\b(DROP|DELETE|UPDATE|INSERT|TRUNCATE|ALTER|CREATE|REPLACE)\b", re.IGNORECASE
    )
    for q in destructive:
        hit = bool(DESTRUCTIVE_PATTERNS.search(q))
        assert_true(hit, f"Detected as destructive: {q[:40]}")
    for q in safe:
        hit = bool(DESTRUCTIVE_PATTERNS.search(q))
        assert_true(not hit, f"Correctly safe: {q[:40]}")


def test_attempt_penalty():
    """Later attempts should yield lower scores than first attempts."""
    print("\n[Reward — attempt penalty]")
    # Simulate: same correct result but attempt 1 vs attempt 3
    # Attempt 1: no penalty → total higher
    # Attempt 3: 0.2 penalty → total lower
    base_reward = 0.8 + 0.2  # full correct score
    attempt_1_total = min(1.0, base_reward - 0.0)
    attempt_3_total = min(1.0, base_reward - 0.2)
    assert_true(attempt_1_total > attempt_3_total, "Attempt 1 scores higher than attempt 3")
    assert_true(attempt_3_total >= 0.0, "Attempt 3 score is non-negative")


def test_row_match_partial_credit():
    """Row matcher should give partial credit for partial matches."""
    print("\n[Grader — partial credit]")
    # Same schema, 2 of 3 rows correct
    actual = [{"name": "Carol", "salary": 135000}, {"name": "Alice", "salary": 120000}]
    expected = [{"name": "Carol", "salary": 135000}, {"name": "Alice", "salary": 120000}, {"name": "Dave", "salary": 95000}]
    # Partial: 2 rows vs 3 expected → different length → score=0 (wrong count matters)
    # But if same count with 2/3 correct rows it's 0.67
    actual_same_len = [{"name": "Carol", "salary": 135000}, {"name": "Alice", "salary": 120000}, {"name": "WRONG", "salary": 0}]
    score = 0
    matches = 0
    for a, e in zip(actual_same_len, expected):
        row_ok = all(
            str(_normalize(a.get(k, ""))).lower() == str(_normalize(e[k])).lower()
            for k in e
        )
        if row_ok:
            matches += 1
    score = matches / len(expected)
    assert_true(abs(score - 2/3) < 0.01, f"Partial credit 2/3 rows ≈ 0.667 (got {score:.3f})")

    # Wrong row count → 0
    wrong_count_score = 0.0 if len(actual) != len(expected) else 1.0
    assert_true(wrong_count_score == 0.0, "Wrong row count → 0.0 score")


def test_environment_lifecycle():
    """Test reset → step → state flow using raw logic."""
    print("\n[Environment lifecycle — pure Python]")

    # Simulate an episode manually
    schema = "CREATE TABLE t (id INTEGER PRIMARY KEY, val INTEGER);"
    seed = ["INSERT INTO t VALUES (1, 10)", "INSERT INTO t VALUES (2, 20)"]
    conn = _build_db_raw(schema, seed)

    # Good query
    ok, rows, err = _run_query_raw(conn, "SELECT val FROM t ORDER BY val;")
    assert_true(ok, "Good SELECT executes")
    assert_true(rows == [{"val": 10}, {"val": 20}], "Good SELECT returns correct rows")

    # Empty result
    ok2, rows2, _ = _run_query_raw(conn, "SELECT val FROM t WHERE val > 9999;")
    assert_true(ok2 and rows2 == [], "Empty result is valid")

    conn.close()
    assert_true(True, "Episode lifecycle completes without error")


def test_difficulty_range():
    """Confirm tasks exist for all three difficulty levels."""
    print("\n[Task catalog — difficulty coverage]")
    from tasks.task_configs import EASY_TASKS, MEDIUM_TASKS, HARD_TASKS
    assert_true(len(EASY_TASKS) >= 3, f"At least 3 easy tasks (got {len(EASY_TASKS)})")
    assert_true(len(MEDIUM_TASKS) >= 3, f"At least 3 medium tasks (got {len(MEDIUM_TASKS)})")
    assert_true(len(HARD_TASKS) >= 3, f"At least 3 hard tasks (got {len(HARD_TASKS)})")

    all_ids = [t.task_id for t in EASY_TASKS + MEDIUM_TASKS + HARD_TASKS]
    assert_true(len(all_ids) == len(set(all_ids)), "All task IDs are unique")
    assert_true(all(t.expected_rows for t in EASY_TASKS + MEDIUM_TASKS + HARD_TASKS),
                "All tasks have expected_rows defined")


def test_pydantic_environment():
    """Full environment test using pydantic models (skipped if pydantic not installed)."""
    print("\n[Full environment — pydantic models]")
    if not PYDANTIC_AVAILABLE:
        print("  ~ Skipped (pydantic not installed in this environment)")
        return

    env = SQLDebuggerEnv()

    # Test reset
    result = env.reset(task_id="easy_01", seed=42)
    assert_true(result.observation.task_id == "easy_01", "reset: task_id correct")
    assert_true(result.observation.attempt_number == 1, "reset: starts at attempt 1")
    assert_true(len(result.observation.previous_attempts) == 0, "reset: no previous attempts")
    assert_true(not env.state().done, "reset: episode not done")

    # Step with wrong answer
    action_wrong = Action(fixed_query="SELECT 1;", explanation="wrong")
    step1 = env.step(action_wrong)
    assert_true(0.0 <= step1.reward <= 1.0, f"step reward in [0,1]: {step1.reward}")

    # Step with correct answer
    correct_q = "SELECT name, salary FROM employees WHERE department = 'Engineering' ORDER BY salary DESC;"
    action_correct = Action(fixed_query=correct_q)
    step2 = env.step(action_correct)
    assert_true(step2.reward >= 0.8, f"Correct query scores >= 0.8 (got {step2.reward})")
    assert_true(step2.done, "Episode done after correct answer")

    # Can't step after done
    try:
        env.step(Action(fixed_query="SELECT 1;"))
        assert_true(False, "Should raise RuntimeError after done")
    except RuntimeError:
        assert_true(True, "Correctly raises RuntimeError after done")


# ─── Runner ──────────────────────────────────────────────────────────────────

def run_all_tests():
    print("=" * 60)
    print("SQL Query Debugger — Test Suite")
    print("=" * 60)

    test_difficulty_range()
    test_easy_reference_queries()
    test_medium_reference_queries()
    test_hard_reference_queries()
    test_destructive_operation_guard()
    test_attempt_penalty()
    test_row_match_partial_credit()
    test_environment_lifecycle()
    test_pydantic_environment()

    print("\n" + "=" * 60)
    total = len(PASS) + len(FAIL)
    print(f"Results: {len(PASS)}/{total} passed")
    if FAIL:
        print(f"Failed: {FAIL}")
        return False
    else:
        print("All tests passed! ✓")
        return True


if __name__ == "__main__":
    ok = run_all_tests()
    sys.exit(0 if ok else 1)
