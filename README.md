---
title: SQL Debugger Environment
emoji: 🧠
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
---

# SQL Query Debugger — OpenEnv Environment

An OpenEnv-compliant environment where AI agents debug broken SQL queries against a live SQLite database. Agents receive a schema, a broken query, and optional error context, then must produce a corrected query that returns the right results.

**Why this matters:** SQL debugging is a daily task for data engineers, analysts, and backend developers. Bugs range from obvious syntax typos to subtle logical errors (wrong JOIN type, integer division, GROUP BY omissions) that execute silently but return wrong data. Automating SQL repair would save significant developer time and is a natural benchmark for code-understanding agents.

---

## Observation Space

Each observation contains:

| Field | Type | Description |
|---|---|---|
| `schema_ddl` | `string` | `CREATE TABLE` statements for all tables |
| `broken_query` | `string` | The SQL query with one or more bugs |
| `error_message` | `string \| null` | Database error from running the broken query (null for silent logic bugs) |
| `expected_description` | `string` | Natural language description of what the correct query should return |
| `attempt_number` | `int` | Current attempt (1–3) |
| `previous_attempts` | `string[]` | All previously submitted queries this episode |
| `task_id` | `string` | Active task identifier |
| `task_difficulty` | `string` | `easy` \| `medium` \| `hard` |

## Action Space

| Field | Type | Description |
|---|---|---|
| `fixed_query` | `string` | The corrected SQL query |
| `explanation` | `string \| null` | Optional: what was wrong and what was fixed |

## Reward Function

Reward is shaped to provide signal throughout the episode — not just at the end:

```
total = (result_correct × 0.8 + execution_score × 0.2) + efficiency_bonus - attempt_penalty

where:
  result_correct    ∈ [0.0, 1.0]   — row-level match vs expected output
  execution_score   = 0.2          — fixed reward for query that runs without error
  efficiency_bonus  ∈ [0.0, 0.1]   — bonus if no anti-patterns (SELECT *, NOT IN)
  attempt_penalty   = (attempt - 1) × 0.1   — 0 on first try, 0.1 on second, 0.2 on third
```

Special cases:
- **Destructive operations** (`DROP`, `DELETE`, `UPDATE`, `TRUNCATE`, etc.) → immediate `0.0`, episode ends
- **Non-executing query** → `0.0` for that attempt, can retry
- **Partial row match** (right schema, wrong rows) → partial credit

## Tasks

### Easy — Single Syntax/Structure Bug

Bugs that produce parse errors or obvious wrong results. The agent just needs to read the error and fix the keyword/clause.

| Task | Bug Type | Example |
|---|---|---|
| `easy_01` | Keyword typos | `SELCT ... FORM ... ORDRE BY` |
| `easy_02` | Clause ordering | `LIMIT` placed after `;` |
| `easy_03` | Spurious `GROUP BY` | Aggregate query accidentally grouped |

**Expected baseline score:** ~0.85–1.0 for frontier models

### Medium — Logic Bugs (Execute but Return Wrong Data)

Bugs that run without error but return incorrect results. The agent must understand query semantics.

| Task | Bug Type | Description |
|---|---|---|
| `medium_01` | LEFT JOIN nullification | `WHERE` clause after LEFT JOIN eliminates NULL rows (should be ON condition) |
| `medium_02` | Partial GROUP BY | `GROUP BY region` instead of `GROUP BY rep_name, region` |
| `medium_03` | Wrong join column | `oi.id` instead of `oi.product_id` in join |

**Expected baseline score:** ~0.5–0.75

### Hard — Multi-Bug & Advanced SQL

Multiple simultaneous bugs in complex queries with CTEs, window functions, or business logic traps.

| Task | Bug Types | Description |
|---|---|---|
| `hard_01` | CTE join mismatch | `dept_avg` joined on `e.id` instead of `e.department_id` |
| `hard_02` | Integer division + LEFT JOIN nullification + HAVING alias | Conversion rate calculation: 3 simultaneous bugs |
| `hard_03` | Arithmetic direction + HAVING alias | `shipped - received` instead of `received - shipped` for in-transit stock |

**Expected baseline score:** ~0.1–0.4 for current frontier models

---

## Setup

### Local (Python)

```bash
git clone <repo-url>
cd sql-debugger-env
pip install -r requirements.txt
python server.py
# Server running on http://localhost:7860
```

### Docker

```bash
docker build -t sql-debugger-env .
docker run -p 7860:7860 sql-debugger-env
```

### Health check

```bash
curl http://localhost:7860/health
# {"status":"ok","env":"sql-query-debugger","version":"1.0.0"}
```

---

## API Usage

### Reset (start episode)

```bash
# Random task
curl -X POST http://localhost:7860/reset -H "Content-Type: application/json" -d '{}'

# Specific task + seed
curl -X POST http://localhost:7860/reset -H "Content-Type: application/json" \
  -d '{"task_id": "medium_01", "seed": 42}'

# By difficulty
curl -X POST http://localhost:7860/reset -H "Content-Type: application/json" \
  -d '{"difficulty": "hard", "seed": 42}'
```

### Step (submit fixed query)

```bash
curl -X POST http://localhost:7860/step -H "Content-Type: application/json" \
  -d '{
    "fixed_query": "SELECT name, salary FROM employees WHERE department = '\''Engineering'\'' ORDER BY salary DESC;",
    "explanation": "Fixed typos: SELCT→SELECT, FORM→FROM, ORDRE BY→ORDER BY"
  }'
```

### State (inspect current episode)

```bash
curl http://localhost:7860/state
```

### List all tasks

```bash
curl http://localhost:7860/tasks
```

---

## Running the Baseline Inference Script

```bash
# Set credentials
export HF_TOKEN=your_api_key_here          # or OPENAI_API_KEY
export API_BASE_URL=https://api.openai.com/v1
export MODEL_NAME=gpt-4o-mini

# Start the environment first
docker run -d -p 7860:7860 sql-debugger-env

# Run inference
python inference.py
```

The script runs the model against `easy_01`, `medium_01`, and `hard_01` with `seed=42` and emits structured `[START]` / `[STEP]` / `[END]` JSON logs.

### Baseline Scores (GPT-4o-mini, seed=42)

| Task | Difficulty | Score |
|---|---|---|
| `easy_01` | Easy | ~0.90 |
| `medium_01` | Medium | ~0.65 |
| `hard_01` | Hard | ~0.25 |
| **Average** | | **~0.60** |

---

## Running Tests

```bash
python tests/test_environment.py
# 39/39 passed

# With pytest (if installed)
python -m pytest tests/ -v
```

---

## Project Structure

```
sql-debugger-env/
├── openenv.yaml            # OpenEnv spec metadata
├── server.py               # FastAPI HTTP server
├── inference.py            # Baseline inference script
├── Dockerfile
├── requirements.txt
├── README.md
├── env/
│   ├── __init__.py
│   ├── models.py           # Pydantic Observation, Action, Reward models
│   ├── environment.py      # Core SQLDebuggerEnv class (reset/step/state)
│   └── grader.py           # SQLite execution + scoring logic
├── tasks/
│   ├── __init__.py
│   └── task_configs.py     # All 9 task definitions (3 easy, 3 medium, 3 hard)
└── tests/
    └── test_environment.py # Full test suite (39 tests)
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `API_BASE_URL` | For inference | LLM API endpoint (e.g. `https://api.openai.com/v1`) |
| `MODEL_NAME` | For inference | Model identifier (e.g. `gpt-4o-mini`) |
| `HF_TOKEN` | For inference | API key (also accepts `OPENAI_API_KEY`) |
| `ENV_BASE_URL` | Optional | Override environment URL (default: `http://localhost:7860`) |

---

## Design Notes

**Why SQLite?** Zero-dependency, deterministic, ships with Python. Every grading run uses a fresh in-memory database seeded from the same INSERT statements, so scores are fully reproducible.

**Why partial credit?** SQL debugging is iterative. The reward function gives signal for "query runs but wrong rows" vs "query errors" vs "query correct" — this lets RL agents learn meaningful intermediate behaviors.

**Why 3 attempts per episode?** Mirrors the real-world developer workflow: see error, fix, re-run. Each attempt incurs a small penalty to reward first-try correctness.

**Hard task design philosophy:** Hard tasks have multiple simultaneous bugs that interact. An agent that fixes only one bug will still fail (non-zero reward for executing, but low result_correct). This creates a gradient that distinguishes shallow pattern-matching from true SQL comprehension.
