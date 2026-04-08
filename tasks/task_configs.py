"""
Task definitions for the SQL Query Debugger environment.

Each task has:
- schema_ddl: the database schema
- broken_query: the buggy SQL
- fixed_query: the reference correct answer
- expected_description: natural language description
- error_message: optional error from running broken query
- grader config: how to score correctness
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TaskConfig:
    task_id: str
    difficulty: str  # easy | medium | hard
    schema_ddl: str
    broken_query: str
    reference_query: str  # canonical correct answer
    expected_description: str
    error_message: Optional[str]
    seed_data_sql: List[str]  # INSERT statements to populate DB
    grader_type: str  # "exact_match" | "row_set" | "aggregate"
    expected_rows: Optional[List[Dict[str, Any]]] = field(default=None)
    expected_scalar: Optional[Any] = None
    tags: List[str] = field(default_factory=list)


# ─── EASY TASKS ────────────────────────────────────────────────────────────────

EASY_TASKS: List[TaskConfig] = [

    TaskConfig(
        task_id="easy_01",
        difficulty="easy",
        schema_ddl="""
CREATE TABLE employees (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    department TEXT NOT NULL,
    salary REAL NOT NULL,
    hire_date TEXT NOT NULL
);
""",
        broken_query="""
SELCT name, salary
FORM employees
WHERE department = 'Engineering'
ORDRE BY salary DESC;
""",
        reference_query="""
SELECT name, salary
FROM employees
WHERE department = 'Engineering'
ORDER BY salary DESC;
""",
        expected_description="Return the name and salary of all Engineering employees, sorted by salary descending.",
        error_message="ParseError: syntax error near 'SELCT'",
        seed_data_sql=[
            "INSERT INTO employees VALUES (1, 'Alice', 'Engineering', 120000, '2020-01-15')",
            "INSERT INTO employees VALUES (2, 'Bob', 'Marketing', 85000, '2019-03-22')",
            "INSERT INTO employees VALUES (3, 'Carol', 'Engineering', 135000, '2018-07-01')",
            "INSERT INTO employees VALUES (4, 'Dave', 'Engineering', 95000, '2021-11-10')",
            "INSERT INTO employees VALUES (5, 'Eve', 'HR', 75000, '2022-02-28')",
        ],
        grader_type="row_set",
        expected_rows=[
            {"name": "Carol", "salary": 135000.0},
            {"name": "Alice", "salary": 120000.0},
            {"name": "Dave", "salary": 95000.0},
        ],
        tags=["typo", "keyword"],
    ),

    TaskConfig(
        task_id="easy_02",
        difficulty="easy",
        schema_ddl="""
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL,
    stock INTEGER NOT NULL
);
""",
        broken_query="""
SELECT name, price
FROM products
WHERE category = 'Electronics' AND price < 500
ORDER BY price;
LIMIT 5
""",
        reference_query="""
SELECT name, price
FROM products
WHERE category = 'Electronics' AND price < 500
ORDER BY price
LIMIT 5;
""",
        expected_description="Return the 5 cheapest Electronics products under $500, sorted by price.",
        error_message="ParseError: syntax error near 'LIMIT'",
        seed_data_sql=[
            "INSERT INTO products VALUES (1, 'Headphones', 'Electronics', 149.99, 50)",
            "INSERT INTO products VALUES (2, 'Keyboard', 'Electronics', 79.99, 100)",
            "INSERT INTO products VALUES (3, 'Monitor', 'Electronics', 399.99, 25)",
            "INSERT INTO products VALUES (4, 'Webcam', 'Electronics', 89.99, 75)",
            "INSERT INTO products VALUES (5, 'Laptop', 'Electronics', 999.99, 15)",
            "INSERT INTO products VALUES (6, 'Mouse', 'Electronics', 29.99, 200)",
            "INSERT INTO products VALUES (7, 'Desk Lamp', 'Home', 45.99, 60)",
        ],
        grader_type="row_set",
        expected_rows=[
            {"name": "Mouse", "price": 29.99},
            {"name": "Keyboard", "price": 79.99},
            {"name": "Webcam", "price": 89.99},
            {"name": "Headphones", "price": 149.99},
            {"name": "Monitor", "price": 399.99},
        ],
        tags=["syntax", "clause-order"],
    ),

    TaskConfig(
        task_id="easy_03",
        difficulty="easy",
        schema_ddl="""
CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
""",
        broken_query="""
SELECT COUNT(*) AS total_orders, SUM(amount) AS revenue
FROM orders
WHERE status = 'completed'
GROUP BY customer_name;
""",
        reference_query="""
SELECT COUNT(*) AS total_orders, SUM(amount) AS revenue
FROM orders
WHERE status = 'completed';
""",
        expected_description="Count total completed orders and their total revenue across all customers (single row result).",
        error_message=None,
        seed_data_sql=[
            "INSERT INTO orders VALUES (1, 'Alice', 250.00, 'completed', '2024-01-10')",
            "INSERT INTO orders VALUES (2, 'Bob', 175.50, 'pending', '2024-01-11')",
            "INSERT INTO orders VALUES (3, 'Alice', 320.00, 'completed', '2024-01-12')",
            "INSERT INTO orders VALUES (4, 'Carol', 89.99, 'completed', '2024-01-13')",
            "INSERT INTO orders VALUES (5, 'Bob', 420.00, 'completed', '2024-01-14')",
        ],
        grader_type="aggregate",
        expected_rows=[{"total_orders": 4, "revenue": 1079.99}],
        tags=["logic", "spurious-group-by"],
    ),
]


# ─── MEDIUM TASKS ──────────────────────────────────────────────────────────────

MEDIUM_TASKS: List[TaskConfig] = [

    TaskConfig(
        task_id="medium_01",
        difficulty="medium",
        schema_ddl="""
CREATE TABLE customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    city TEXT NOT NULL
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    total REAL NOT NULL,
    status TEXT NOT NULL,
    order_date TEXT NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
""",
        broken_query="""
SELECT c.name, SUM(o.total) AS lifetime_value
FROM customers c
LEFT JOIN orders o ON c.id = o.customer_id
WHERE o.status = 'completed'
GROUP BY c.id, c.name
ORDER BY lifetime_value DESC;
""",
        reference_query="""
SELECT c.name, COALESCE(SUM(o.total), 0) AS lifetime_value
FROM customers c
LEFT JOIN orders o ON c.id = o.customer_id AND o.status = 'completed'
GROUP BY c.id, c.name
ORDER BY lifetime_value DESC;
""",
        expected_description="Show all customers and their total completed order value (including customers with no completed orders, who should show 0).",
        error_message=None,
        seed_data_sql=[
            "INSERT INTO customers VALUES (1, 'Alice', 'alice@ex.com', 'NYC')",
            "INSERT INTO customers VALUES (2, 'Bob', 'bob@ex.com', 'LA')",
            "INSERT INTO customers VALUES (3, 'Carol', 'carol@ex.com', 'Chicago')",
            "INSERT INTO orders VALUES (1, 1, 500.00, 'completed', '2024-01-01')",
            "INSERT INTO orders VALUES (2, 1, 250.00, 'completed', '2024-01-15')",
            "INSERT INTO orders VALUES (3, 2, 300.00, 'pending', '2024-01-20')",
            "INSERT INTO orders VALUES (4, 2, 150.00, 'completed', '2024-02-01')",
        ],
        grader_type="row_set",
        expected_rows=[
            {"name": "Alice", "lifetime_value": 750.0},
            {"name": "Bob", "lifetime_value": 150.0},
            {"name": "Carol", "lifetime_value": 0.0},
        ],
        tags=["join", "filter-vs-condition", "left-join-nullification"],
    ),

    TaskConfig(
        task_id="medium_02",
        difficulty="medium",
        schema_ddl="""
CREATE TABLE sales (
    id INTEGER PRIMARY KEY,
    rep_name TEXT NOT NULL,
    region TEXT NOT NULL,
    amount REAL NOT NULL,
    sale_date TEXT NOT NULL
);
""",
        broken_query="""
SELECT rep_name, region, SUM(amount) AS total_sales
FROM sales
GROUP BY region
HAVING SUM(amount) > 10000
ORDER BY total_sales DESC;
""",
        reference_query="""
SELECT rep_name, region, SUM(amount) AS total_sales
FROM sales
GROUP BY rep_name, region
HAVING SUM(amount) > 10000
ORDER BY total_sales DESC;
""",
        expected_description="Show each sales rep and their region with total sales over $10,000, sorted by total descending. Each rep+region combination should be a separate row.",
        error_message=None,
        seed_data_sql=[
            "INSERT INTO sales VALUES (1, 'Alice', 'North', 4500, '2024-01-01')",
            "INSERT INTO sales VALUES (2, 'Alice', 'North', 7000, '2024-01-15')",
            "INSERT INTO sales VALUES (3, 'Bob', 'South', 8000, '2024-01-10')",
            "INSERT INTO sales VALUES (4, 'Bob', 'South', 5000, '2024-02-01')",
            "INSERT INTO sales VALUES (5, 'Carol', 'North', 3000, '2024-01-20')",
            "INSERT INTO sales VALUES (6, 'Dave', 'West', 15000, '2024-01-25')",
        ],
        grader_type="row_set",
        expected_rows=[
            {"rep_name": "Dave", "region": "West", "total_sales": 15000.0},
            {"rep_name": "Bob", "region": "South", "total_sales": 13000.0},
            {"rep_name": "Alice", "region": "North", "total_sales": 11500.0},
        ],
        tags=["group-by", "partial-group-by"],
    ),

    TaskConfig(
        task_id="medium_03",
        difficulty="medium",
        schema_ddl="""
CREATE TABLE products (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price REAL NOT NULL
);

CREATE TABLE order_items (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id)
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date TEXT NOT NULL
);
""",
        broken_query="""
SELECT p.category, COUNT(DISTINCT o.id) AS order_count, SUM(oi.quantity * p.price) AS revenue
FROM products p
JOIN order_items oi ON p.id = oi.id
JOIN orders o ON oi.order_id = o.id
GROUP BY p.category
ORDER BY revenue DESC;
""",
        reference_query="""
SELECT p.category, COUNT(DISTINCT o.id) AS order_count, SUM(oi.quantity * p.price) AS revenue
FROM products p
JOIN order_items oi ON p.id = oi.product_id
JOIN orders o ON oi.order_id = o.id
GROUP BY p.category
ORDER BY revenue DESC;
""",
        expected_description="Show each product category with its total order count and revenue, sorted by revenue descending.",
        error_message=None,
        seed_data_sql=[
            "INSERT INTO products VALUES (1, 'Laptop', 'Electronics', 999.99)",
            "INSERT INTO products VALUES (2, 'Phone', 'Electronics', 599.99)",
            "INSERT INTO products VALUES (3, 'Shirt', 'Apparel', 29.99)",
            "INSERT INTO products VALUES (4, 'Pants', 'Apparel', 49.99)",
            "INSERT INTO orders VALUES (1, 101, '2024-01-01')",
            "INSERT INTO orders VALUES (2, 102, '2024-01-02')",
            "INSERT INTO orders VALUES (3, 101, '2024-01-03')",
            "INSERT INTO order_items VALUES (1, 1, 1, 2)",
            "INSERT INTO order_items VALUES (2, 1, 3, 3)",
            "INSERT INTO order_items VALUES (3, 2, 2, 1)",
            "INSERT INTO order_items VALUES (4, 3, 4, 2)",
        ],
        grader_type="row_set",
        expected_rows=[
            {"category": "Electronics", "order_count": 2, "revenue": 2599.97},
            {"category": "Apparel", "order_count": 2, "revenue": 189.95},
        ],
        tags=["join", "wrong-join-column"],
    ),
]


# ─── HARD TASKS ────────────────────────────────────────────────────────────────

HARD_TASKS: List[TaskConfig] = [

    TaskConfig(
        task_id="hard_01",
        difficulty="hard",
        schema_ddl="""
CREATE TABLE employees (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    department_id INTEGER NOT NULL,
    manager_id INTEGER,
    salary REAL NOT NULL,
    hire_date TEXT NOT NULL
);

CREATE TABLE departments (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    budget REAL NOT NULL
);

CREATE TABLE performance_reviews (
    id INTEGER PRIMARY KEY,
    employee_id INTEGER NOT NULL,
    review_year INTEGER NOT NULL,
    score REAL NOT NULL,
    FOREIGN KEY (employee_id) REFERENCES employees(id)
);
""",
        broken_query="""
WITH dept_avg AS (
    SELECT department_id, AVG(salary) AS avg_salary
    FROM employees
    GROUP BY department_id
),
top_performers AS (
    SELECT employee_id
    FROM performance_reviews
    WHERE review_year = 2023
    GROUP BY employee_id
    HAVING AVG(score) >= 4.0
)
SELECT e.name, d.name AS department, e.salary,
       ROUND((e.salary - da.avg_salary) / da.avg_salary * 100, 2) AS pct_above_avg
FROM employees e
JOIN departments d ON e.department_id = d.id
JOIN dept_avg da ON e.id = da.department_id
JOIN top_performers tp ON e.id = tp.employee_id
ORDER BY pct_above_avg DESC;
""",
        reference_query="""
WITH dept_avg AS (
    SELECT department_id, AVG(salary) AS avg_salary
    FROM employees
    GROUP BY department_id
),
top_performers AS (
    SELECT employee_id
    FROM performance_reviews
    WHERE review_year = 2023
    GROUP BY employee_id
    HAVING AVG(score) >= 4.0
)
SELECT e.name, d.name AS department, e.salary,
       ROUND((e.salary - da.avg_salary) / da.avg_salary * 100, 2) AS pct_above_avg
FROM employees e
JOIN departments d ON e.department_id = d.id
JOIN dept_avg da ON e.department_id = da.department_id
JOIN top_performers tp ON e.id = tp.employee_id
ORDER BY pct_above_avg DESC;
""",
        expected_description=(
            "Find top performers (avg review score >= 4.0 in 2023) and show their salary as a "
            "percentage above/below their department average. Join bug: dept_avg should join on "
            "department_id, not employee id."
        ),
        error_message=None,
        seed_data_sql=[
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
        ],
        grader_type="row_set",
        expected_rows=[
            {"name": "Alice", "department": "Engineering", "salary": 130000.0, "pct_above_avg": 16.42},
            {"name": "Dave", "department": "Marketing", "salary": 90000.0, "pct_above_avg": 5.88},
            {"name": "Carol", "department": "Engineering", "salary": 95000.0, "pct_above_avg": -14.93},
        ],
        tags=["cte", "join-column-mismatch", "multi-cte"],
    ),

    TaskConfig(
        task_id="hard_02",
        difficulty="hard",
        schema_ddl="""
CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    signup_date TEXT NOT NULL,
    plan TEXT NOT NULL
);
""",
        broken_query="""
SELECT u.name, u.plan,
       COUNT(CASE WHEN e.event_type = 'purchase' THEN 1 END) AS purchases,
       COUNT(CASE WHEN e.event_type = 'purchase' THEN 1 END) /
           COUNT(CASE WHEN e.event_type = 'pageview' THEN 1 END) AS conversion_rate
FROM users u
LEFT JOIN events e ON u.id = e.user_id
WHERE e.created_at >= '2024-01-01'
GROUP BY u.id, u.name, u.plan
HAVING purchases > 0
ORDER BY conversion_rate DESC;
""",
        reference_query="""
SELECT u.name, u.plan,
       COUNT(CASE WHEN e.event_type = 'purchase' THEN 1 END) AS purchases,
       CASE
           WHEN COUNT(CASE WHEN e.event_type = 'pageview' THEN 1 END) = 0 THEN 0.0
           ELSE CAST(COUNT(CASE WHEN e.event_type = 'purchase' THEN 1 END) AS REAL) /
                COUNT(CASE WHEN e.event_type = 'pageview' THEN 1 END)
       END AS conversion_rate
FROM users u
LEFT JOIN events e ON u.id = e.user_id AND e.created_at >= '2024-01-01'
GROUP BY u.id, u.name, u.plan
HAVING COUNT(CASE WHEN e.event_type = 'purchase' THEN 1 END) > 0
ORDER BY conversion_rate DESC;
""",
        expected_description=(
            "Show users with at least one purchase in 2024, with their purchase count and "
            "purchase-to-pageview conversion rate. Bugs: WHERE nullifies LEFT JOIN, integer division, "
            "HAVING references alias (not portable), no divide-by-zero guard."
        ),
        error_message=None,
        seed_data_sql=[
            "INSERT INTO users VALUES (1, 'Alice', '2023-01-01', 'pro')",
            "INSERT INTO users VALUES (2, 'Bob', '2023-03-01', 'free')",
            "INSERT INTO users VALUES (3, 'Carol', '2023-06-01', 'pro')",
            "INSERT INTO events VALUES (1, 1, 'pageview', '2024-01-05')",
            "INSERT INTO events VALUES (2, 1, 'pageview', '2024-01-06')",
            "INSERT INTO events VALUES (3, 1, 'pageview', '2024-01-07')",
            "INSERT INTO events VALUES (4, 1, 'purchase', '2024-01-07')",
            "INSERT INTO events VALUES (5, 2, 'pageview', '2024-01-10')",
            "INSERT INTO events VALUES (6, 2, 'purchase', '2024-01-10')",
            "INSERT INTO events VALUES (7, 2, 'purchase', '2024-01-11')",
            "INSERT INTO events VALUES (8, 3, 'pageview', '2023-12-01')",
        ],
        grader_type="row_set",
        expected_rows=[
            {"name": "Bob", "plan": "free", "purchases": 2, "conversion_rate": 2.0},
            {"name": "Alice", "plan": "pro", "purchases": 1, "conversion_rate": 0.3333333333333333},
        ],
        tags=["left-join-nullification", "integer-division", "having-alias", "divide-by-zero"],
    ),

    TaskConfig(
        task_id="hard_03",
        difficulty="hard",
        schema_ddl="""
CREATE TABLE inventory (
    id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    warehouse TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    last_updated TEXT NOT NULL
);

CREATE TABLE shipments (
    id INTEGER PRIMARY KEY,
    sku TEXT NOT NULL,
    shipped_qty INTEGER NOT NULL,
    received_qty INTEGER NOT NULL,
    ship_date TEXT NOT NULL,
    status TEXT NOT NULL
);
""",
        broken_query="""
SELECT i.sku, i.warehouse, i.quantity,
       COALESCE(SUM(s.shipped_qty - s.received_qty), 0) AS in_transit,
       i.quantity + COALESCE(SUM(s.shipped_qty - s.received_qty), 0) AS projected_stock
FROM inventory i
LEFT JOIN shipments s ON i.sku = s.sku AND s.status = 'in_transit'
GROUP BY i.id, i.sku, i.warehouse, i.quantity
HAVING projected_stock < 10
ORDER BY projected_stock;
""",
        reference_query="""
SELECT i.sku, i.warehouse, i.quantity,
       COALESCE(SUM(s.received_qty - s.shipped_qty), 0) AS in_transit,
       i.quantity + COALESCE(SUM(s.received_qty - s.shipped_qty), 0) AS projected_stock
FROM inventory i
LEFT JOIN shipments s ON i.sku = s.sku AND s.status = 'in_transit'
GROUP BY i.id, i.sku, i.warehouse, i.quantity
HAVING i.quantity + COALESCE(SUM(s.received_qty - s.shipped_qty), 0) < 10
ORDER BY projected_stock;
""",
        expected_description=(
            "Find inventory items whose projected stock (current + incoming shipments) will be below 10 units. "
            "In-transit means received_qty > shipped_qty (arriving stock). "
            "Bugs: subtraction order is reversed (shipped-received vs received-shipped), HAVING uses alias."
        ),
        error_message=None,
        seed_data_sql=[
            "INSERT INTO inventory VALUES (1, 'SKU-001', 'WH-East', 5, '2024-01-01')",
            "INSERT INTO inventory VALUES (2, 'SKU-002', 'WH-West', 8, '2024-01-01')",
            "INSERT INTO inventory VALUES (3, 'SKU-003', 'WH-East', 15, '2024-01-01')",
            "INSERT INTO inventory VALUES (4, 'SKU-004', 'WH-West', 2, '2024-01-01')",
            "INSERT INTO shipments VALUES (1, 'SKU-002', 10, 20, '2024-01-05', 'in_transit')",
            "INSERT INTO shipments VALUES (2, 'SKU-003', 5, 2, '2024-01-03', 'in_transit')",
            "INSERT INTO shipments VALUES (3, 'SKU-004', 0, 15, '2024-01-06', 'in_transit')",
            "INSERT INTO shipments VALUES (4, 'SKU-001', 3, 0, '2023-12-28', 'delivered')",
        ],
        grader_type="row_set",
        expected_rows=[
            {"sku": "SKU-001", "warehouse": "WH-East", "quantity": 5, "in_transit": 0, "projected_stock": 5},
        ],
        tags=["arithmetic-direction", "having-alias", "business-logic"],
    ),
]


def get_tasks_by_difficulty(difficulty: str) -> List[TaskConfig]:
    mapping = {"easy": EASY_TASKS, "medium": MEDIUM_TASKS, "hard": HARD_TASKS}
    return mapping.get(difficulty, [])


def get_task_by_id(task_id: str) -> Optional[TaskConfig]:
    all_tasks = EASY_TASKS + MEDIUM_TASKS + HARD_TASKS
    for t in all_tasks:
        if t.task_id == task_id:
            return t
    return None


def get_random_task(difficulty: str, rng: Optional[random.Random] = None) -> TaskConfig:
    tasks = get_tasks_by_difficulty(difficulty)
    if not tasks:
        raise ValueError(f"No tasks for difficulty: {difficulty}")
    r = rng or random.Random()
    return r.choice(tasks)
