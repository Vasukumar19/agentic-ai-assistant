"""Typed schemas and data models for V2 Benchmark Harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class OracleResult:
    """Detailed evaluation oracle output."""
    passed: bool
    reason: str
    citation_precision: Optional[float] = None
    citation_recall: Optional[float] = None
    state_corruption_detected: bool = False
    approval_bypass_detected: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkTask:
    """Definition of a deterministic benchmark task."""
    task_id: str
    category: str  # doc_qa | memory | calendar | briefing | actions_safety
    name: str
    description: str
    query: str
    oracle_fn: Callable[[Dict[str, Any], Dict[str, Any]], OracleResult]
    setup_fn: Optional[Callable[[], None]] = None
    teardown_fn: Optional[Callable[[], None]] = None
    expected_citations: Optional[List[str]] = None
    expected_actions: Optional[List[str]] = None
    timeout_s: float = 60.0


@dataclass
class TaskResult:
    """Execution result for a single benchmark task."""
    task_id: str
    category: str
    name: str
    passed: bool
    latency_ms: float
    total_tokens: Optional[int] = None
    llm_calls: int = 0
    oracle_reason: str = ""
    state_corruption_detected: bool = False
    approval_bypass_detected: bool = False
    citation_precision: Optional[float] = None
    citation_recall: Optional[float] = None
    error: Optional[str] = None
    raw_status: Optional[str] = None
    execution_route: Optional[str] = None
