"""
inference.py — Baseline inference script for SQL Query Debugger OpenEnv.

Runs a language model against all 3 task difficulties and reports scores.
Uses the OpenAI client as required by the competition spec.

Environment variables:
  API_BASE_URL   The API endpoint for the LLM (default: https://api.openai.com/v1)
  MODEL_NAME     The model identifier (default: gpt-4o-mini)
  HF_TOKEN       Your HuggingFace / API key (used as OpenAI API key)
  ENV_BASE_URL   The running environment URL (default: http://localhost:7860)

Usage:
  python inference.py

Stdout logging follows the required [START] / [STEP] / [END] format.
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional

import requests
from openai import OpenAI

# ─── Configuration ────────────────────────────────────────────────────────────

API_BASE_URL: str = os.environ.get("API_BASE_URL", "https://api.openai.com/v1")
MODEL_NAME: str = os.environ.get("MODEL_NAME", "gpt-4o-mini")
API_KEY: str = os.environ.get("HF_TOKEN", os.environ.get("OPENAI_API_KEY", ""))
ENV_BASE_URL: str = os.environ.get("ENV_BASE_URL", "http://localhost:7860")

MAX_STEPS: int = 3
MAX_TOTAL_REWARD: float = 1.0
SUCCESS_SCORE_THRESHOLD: float = 0.8
BENCHMARK: str = "sql-query-debugger"

TASKS_TO_RUN = [
    {"task_id": "easy_01",   "difficulty": "easy"},
    {"task_id": "medium_01", "difficulty": "medium"},
    {"task_id": "hard_01",   "difficulty": "hard"},
]


# ─── Structured logging (required format) ─────────────────────────────────────
def log_start(task: str, env: str, model: str) -> None:
    print(f"[START] task={task} env={env} model={model}", flush=True)


def log_step(
    step: int,
    action: str,
    reward: float,
    done: bool,
    error: Optional[str],
) -> None:
    action_str = action.replace("\n", " ")[:200]  # keep single line
    error_val = error if error else "null"
    done_val = str(done).lower()

    print(
        f"[STEP] step={step} action={action_str} reward={reward:.2f} done={done_val} error={error_val}",
        flush=True,
    )


def log_end(
    success: bool,
    steps: int,
    score: float,
    rewards: List[float],
) -> None:
    rewards_str = ",".join(f"{r:.2f}" for r in rewards)

    print(
        f"[END] success={str(success).lower()} steps={steps} score={score:.2f} rewards={rewards_str}",
        flush=True,
    )

# ─── Environment HTTP client ──────────────────────────────────────────────────

def env_reset(task_id: str, seed: int = 42) -> Dict[str, Any]:
    r = requests.post(
        f"{ENV_BASE_URL}/reset",
        json={"task_id": task_id, "seed": seed},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def env_step(fixed_query: str, explanation: str = "") -> Dict[str, Any]:
    r = requests.post(
        f"{ENV_BASE_URL}/step",
        json={"fixed_query": fixed_query, "explanation": explanation},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ─── LLM agent ───────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert SQL debugger. You will be given:
1. A database schema (CREATE TABLE statements)
2. A broken SQL query that contains one or more bugs
3. An optional error message from running the broken query
4. A description of what the correct query should return

Your job is to fix the SQL query so it correctly returns the described results.

IMPORTANT: Respond with ONLY a JSON object in this exact format:
{
  "fixed_query": "<your corrected SQL here>",
  "explanation": "<brief explanation of what was wrong>"
}

Do not include markdown code blocks, just the raw JSON.
Do not change the intent of the query — only fix the bugs."""


def build_user_prompt(obs: Dict[str, Any], last_reward: float, attempt: int) -> str:
    parts = [
        f"=== Schema ===\n{obs['schema_ddl']}",
        f"=== Broken Query ===\n{obs['broken_query']}",
    ]
    if obs.get("error_message"):
        parts.append(f"=== Error Message ===\n{obs['error_message']}")
    parts.append(f"=== What the Query Should Return ===\n{obs['expected_description']}")
    if obs.get("previous_attempts"):
        parts.append(f"=== Your Previous Attempts (all scored {last_reward:.2f}) ===")
        for i, prev in enumerate(obs["previous_attempts"], 1):
            parts.append(f"Attempt {i}:\n{prev}")
        parts.append("Try a different approach.")
    parts.append(f"\n(Attempt {attempt} of 3 — higher attempts reduce your score)")
    return "\n\n".join(parts)


def get_model_action(
    client: OpenAI,
    obs: Dict[str, Any],
    last_reward: float,
    history: List[Dict],
) -> tuple[str, str]:
    """Call the LLM and parse fixed_query + explanation."""
    user_msg = build_user_prompt(obs, last_reward, obs.get("attempt_number", 1))
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    # Include recent history for context
    for h in history[-2:]:
        messages.append({"role": "user", "content": h["user"]})
        messages.append({"role": "assistant", "content": h["assistant"]})
    messages.append({"role": "user", "content": user_msg})

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            max_tokens=1000,
            temperature=0.1,
        )
        raw = (completion.choices[0].message.content or "").strip()

        # Parse JSON response
        # Handle potential markdown wrapping
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw.strip())
        fixed_query = parsed.get("fixed_query", "").strip()
        explanation = parsed.get("explanation", "")
        if fixed_query:
            return fixed_query, explanation
    except Exception as exc:
        print(f"[DEBUG] LLM parse error: {exc}", flush=True)

    # Fallback: return broken query as-is (will score 0)
    return obs.get("broken_query", "SELECT 1"), "Parse error — returning original"


# ─── Main loop ───────────────────────────────────────────────────────────────

def run_task(client: OpenAI, task_cfg: Dict[str, Any]) -> float:
    task_id = task_cfg["task_id"]
    log_start(task=task_id, env=BENCHMARK, model=MODEL_NAME)

    rewards: List[float] = []
    steps_taken = 0
    score = 0.0
    success = False
    history: List[Dict] = []
    last_reward = 0.0

    try:
        result = env_reset(task_id, seed=42)
        obs = result["observation"]

        for step in range(1, MAX_STEPS + 1):
            if result.get("done", False):
                break

            fixed_query, explanation = get_model_action(client, obs, last_reward, history)
            history.append({"user": build_user_prompt(obs, last_reward, step), "assistant":
                            json.dumps({"fixed_query": fixed_query, "explanation": explanation})})

            result = env_step(fixed_query, explanation)
            obs = result["observation"]
            reward = result.get("reward", 0.0)
            done = result.get("done", False)

            rewards.append(reward)
            last_reward = reward
            steps_taken = step

            log_step(step=step, action=fixed_query, reward=reward, done=done, error=None)

            if done:
                break

        score = max(rewards) if rewards else 0.0
        score = round(min(max(score, 0.0), 1.0), 4)
        success = score >= SUCCESS_SCORE_THRESHOLD

    except Exception as exc:
        print(f"[DEBUG] Task {task_id} error: {exc}", flush=True)
        log_step(step=steps_taken, action="ERROR", reward=0.0, done=True, error=str(exc))

    log_end(success=success, steps=steps_taken, score=score, rewards=rewards)
    return score


def main() -> None:
    if not API_KEY:
        print("[ERROR] Set HF_TOKEN or OPENAI_API_KEY environment variable.", file=sys.stderr)
        sys.exit(1)

    # Wait for env to be ready
    for attempt in range(10):
        try:
            r = requests.get(f"{ENV_BASE_URL}/health", timeout=5)
            if r.status_code == 200:
                break
        except Exception:
            pass
        print(f"[DEBUG] Waiting for environment... ({attempt + 1}/10)", flush=True)
        time.sleep(3)
    else:
        print("[ERROR] Environment not reachable.", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(base_url=API_BASE_URL, api_key=API_KEY)

    all_scores: List[float] = []
    for task_cfg in TASKS_TO_RUN:
        score = run_task(client, task_cfg)
        all_scores.append(score)
        print(f"[RESULT] {task_cfg['task_id']}: {score:.4f}", flush=True)

    avg = sum(all_scores) / len(all_scores)
    print(f"\n[SUMMARY] Scores: {all_scores}", flush=True)
    print(f"[SUMMARY] Average: {avg:.4f}", flush=True)
    print(f"[SUMMARY] Tasks passed (>={SUCCESS_SCORE_THRESHOLD}): "
          f"{sum(1 for s in all_scores if s >= SUCCESS_SCORE_THRESHOLD)}/{len(all_scores)}", flush=True)


if __name__ == "__main__":
    main()
