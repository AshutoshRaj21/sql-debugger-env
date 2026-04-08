"""
SQL Query Debugger — OpenEnv environment core.

Implements:
  reset(task_id?, seed?) -> ResetResult
  step(action) -> StepResult
  state() -> StateResult
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from env.grader import grade
from env.models import (
    Action,
    Observation,
    Reward,
    ResetResult,
    StateResult,
    StepResult,
)
from tasks.task_configs import (
    TaskConfig,
    get_random_task,
    get_task_by_id,
)


MAX_ATTEMPTS = 3


class SQLDebuggerEnv:
    """
    OpenEnv-compliant SQL Query Debugger environment.

    The agent receives a broken SQL query + schema and must submit
    a corrected query. It gets up to 3 attempts with decreasing reward.
    """

    def __init__(self) -> None:
        self._task: Optional[TaskConfig] = None
        self._attempt: int = 0
        self._done: bool = True
        self._episode_rewards: List[float] = []
        self._previous_attempts: List[str] = []
        self._last_observation: Optional[Observation] = None
        self._rng = random.Random()

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def reset(
        self,
        task_id: Optional[str] = None,
        difficulty: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> ResetResult:
        """
        Start a new episode.

        Args:
            task_id: Specific task to run (e.g. "easy_01"). If None, picks randomly.
            difficulty: "easy" | "medium" | "hard". Used when task_id is None.
            seed: Random seed for reproducibility.

        Returns:
            ResetResult with initial observation.
        """
        if seed is not None:
            self._rng = random.Random(seed)

        if task_id:
            task = get_task_by_id(task_id)
            if task is None:
                raise ValueError(f"Unknown task_id: {task_id}")
        else:
            diff = difficulty or self._rng.choice(["easy", "medium", "hard"])
            task = get_random_task(diff, rng=self._rng)

        self._task = task
        self._attempt = 0
        self._done = False
        self._episode_rewards = []
        self._previous_attempts = []

        obs = self._build_observation()
        self._last_observation = obs

        return ResetResult(
            observation=obs,
            info={
                "task_id": task.task_id,
                "difficulty": task.difficulty,
                "tags": task.tags,
                "max_attempts": MAX_ATTEMPTS,
            },
        )

    def step(self, action: Action) -> StepResult:
        """
        Submit a fixed query.

        Args:
            action: Action with fixed_query (and optional explanation).

        Returns:
            StepResult with observation, reward, done flag, and info.
        """
        if self._done:
            raise RuntimeError("Episode is done. Call reset() to start a new episode.")
        if self._task is None:
            raise RuntimeError("No active task. Call reset() first.")

        self._attempt += 1
        fixed_query = action.fixed_query.strip()

        # Grade the submission
        reward_breakdown = grade(
            task=self._task,
            fixed_query=fixed_query,
            attempt_number=self._attempt,
            max_attempts=MAX_ATTEMPTS,
        )
        reward_value = reward_breakdown.total
        self._episode_rewards.append(reward_value)
        self._previous_attempts.append(fixed_query)

        # Episode ends when: perfect score, max attempts reached, or destructive op
        perfect = reward_breakdown.result_correct >= 1.0 and reward_breakdown.executes
        exhausted = self._attempt >= MAX_ATTEMPTS
        unsafe = not reward_breakdown.no_destructive_ops

        done = perfect or exhausted or unsafe
        self._done = done

        # Build next observation (shows feedback if not done)
        if done:
            obs = self._last_observation  # terminal: return last obs
        else:
            obs = self._build_observation()
            self._last_observation = obs

        return StepResult(
            observation=obs,
            reward=reward_value,
            reward_breakdown=reward_breakdown,
            done=done,
            info={
                "attempt": self._attempt,
                "max_attempts": MAX_ATTEMPTS,
                "perfect": perfect,
                "exhausted": exhausted,
                "unsafe": unsafe,
                "executes": reward_breakdown.executes,
                "result_correct": reward_breakdown.result_correct,
                "explanation": action.explanation,
            },
        )

    def state(self) -> StateResult:
        """Return current internal state for inspection/debugging."""
        return StateResult(
            task_id=self._task.task_id if self._task else "",
            current_attempt=self._attempt,
            max_attempts=MAX_ATTEMPTS,
            episode_rewards=list(self._episode_rewards),
            done=self._done,
            current_observation=self._last_observation,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _build_observation(self) -> Observation:
        assert self._task is not None
        return Observation(
            schema_ddl=self._task.schema_ddl.strip(),
            broken_query=self._task.broken_query.strip(),
            error_message=self._task.error_message,
            expected_description=self._task.expected_description,
            attempt_number=self._attempt + 1,
            previous_attempts=list(self._previous_attempts),
            task_id=self._task.task_id,
            task_difficulty=self._task.difficulty,
        )
