"""
Pydantic models for the SQL Query Debugger OpenEnv environment.
Defines Observation, Action, Reward, and supporting types.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Observation(BaseModel):
    """What the agent sees at each step."""

    schema_ddl: str = Field(
        description="CREATE TABLE statements defining the database schema"
    )
    broken_query: str = Field(
        description="The SQL query containing one or more bugs"
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Database error from running the broken query (may be None for logic bugs)"
    )
    expected_description: str = Field(
        description="Natural language description of what the fixed query should return"
    )
    attempt_number: int = Field(
        default=1,
        ge=1,
        description="Current attempt number (1-indexed)"
    )
    previous_attempts: List[str] = Field(
        default_factory=list,
        description="Previously submitted queries in this episode"
    )
    task_id: str = Field(description="Which task is active")
    task_difficulty: str = Field(description="easy | medium | hard")


class Action(BaseModel):
    """The agent's response — a corrected SQL query."""

    fixed_query: str = Field(
        description="The corrected SQL query the agent believes solves the problem"
    )
    explanation: Optional[str] = Field(
        default=None,
        description="Optional explanation of the bug and fix"
    )


class Reward(BaseModel):
    """Structured reward breakdown for interpretability."""

    total: float = Field(ge=0.0, le=1.0, description="Overall reward [0, 1]")
    executes: bool = Field(description="True if the fixed query runs without error")
    result_correct: float = Field(
        ge=0.0, le=1.0,
        description="How closely output matches expected (0=wrong, 1=perfect)"
    )
    no_destructive_ops: bool = Field(
        description="True if query has no DROP/DELETE/UPDATE/TRUNCATE"
    )
    efficiency_bonus: float = Field(
        ge=0.0, le=0.2,
        description="Small bonus for efficient query (no N+1, uses indexes)"
    )
    attempt_penalty: float = Field(
        ge=0.0, le=0.3,
        description="Penalty applied for using multiple attempts"
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Extra grader details for debugging"
    )


class StepResult(BaseModel):
    """Full result returned from step()."""

    observation: Observation
    reward: float = Field(ge=0.0, le=1.0)
    reward_breakdown: Reward
    done: bool
    info: Dict[str, Any] = Field(default_factory=dict)


class ResetResult(BaseModel):
    """Result returned from reset()."""

    observation: Observation
    info: Dict[str, Any] = Field(default_factory=dict)


class StateResult(BaseModel):
    """Current internal environment state (for debugging/inspection)."""

    task_id: str
    current_attempt: int
    max_attempts: int
    episode_rewards: List[float]
    done: bool
    current_observation: Optional[Observation] = None
