"""
FastAPI server for the SQL Query Debugger OpenEnv environment.

Exposes:
  POST /reset   — start new episode
  POST /step    — submit a fixed query
  GET  /state   — inspect current state
  GET  /health  — liveness check
"""
from __future__ import annotations

from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from env.environment import SQLDebuggerEnv
from env.models import Action, ResetResult, StateResult, StepResult

app = FastAPI(
    title="SQL Query Debugger — OpenEnv",
    description=(
        "An OpenEnv environment where AI agents debug broken SQL queries. "
        "Supports 3 difficulty levels: easy (syntax errors), medium (logic/join bugs), "
        "and hard (multi-bug CTE/window function queries)."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single shared environment instance (stateful)
_env = SQLDebuggerEnv()


# ─── Request/Response models ──────────────────────────────────────────────────

class ResetRequest(BaseModel):
    task_id: Optional[str] = None
    difficulty: Optional[str] = None
    seed: Optional[int] = None


class StepRequest(BaseModel):
    fixed_query: str
    explanation: Optional[str] = None


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "env": "sql-query-debugger", "version": "1.0.0"}


@app.post("/reset", response_model=ResetResult)
async def reset(req: ResetRequest = ResetRequest()):
    try:
        result = _env.reset(
            task_id=req.task_id,
            difficulty=req.difficulty,
            seed=req.seed,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reset failed: {e}")


@app.post("/step", response_model=StepResult)
async def step(req: StepRequest):
    try:
        action = Action(fixed_query=req.fixed_query, explanation=req.explanation)
        result = _env.step(action)
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Step failed: {e}")


@app.get("/state", response_model=StateResult)
async def state():
    return _env.state()


@app.get("/tasks")
async def list_tasks():
    """List all available tasks with metadata."""
    from tasks.task_configs import EASY_TASKS, MEDIUM_TASKS, HARD_TASKS
    tasks = []
    for t in EASY_TASKS + MEDIUM_TASKS + HARD_TASKS:
        tasks.append({
            "task_id": t.task_id,
            "difficulty": t.difficulty,
            "description": t.expected_description[:100] + "...",
            "tags": t.tags,
        })
    return {"tasks": tasks, "total": len(tasks)}


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=7860, reload=False)
