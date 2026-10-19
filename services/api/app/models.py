"""Response shapes.

These models are the privacy boundary: `question_text` and `sql_text` exist
as columns but are deliberately absent here, so no endpoint can expose them
even if a query selects them by accident.
"""
from datetime import datetime

from pydantic import BaseModel, Field


class Summary(BaseModel):
    window_hours: int = Field(description="Size of the window these figures cover.")
    total_requests: int
    cache_hits: int
    cache_hit_rate_pct: float | None = Field(
        description="Null when there were no requests in the window."
    )
    errors: int
    error_rate_pct: float | None
    fallback_requests: int = Field(
        description="Model-backed requests finally answered by the fallback provider."
    )
    fallback_rate_pct: float | None
    total_cost_usd: float


class LatencyStats(BaseModel):
    window_hours: int
    cache_hits_excluded: bool = True
    sample_size: int
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    max_ms: int | None


class ProviderStats(BaseModel):
    provider: str
    model: str
    calls: int
    successes: int
    failures: int
    success_rate_pct: float
    p50_ms: float | None
    p95_ms: float | None
    input_tokens: int
    output_tokens: int
    cost_usd: float


class DailyCost(BaseModel):
    day: datetime
    provider: str
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class TraceSummary(BaseModel):
    """One row in a trace listing. Carries no prompt or SQL text."""

    trace_id: str
    started_at: datetime
    duration_ms: int | None
    status: str
    error_type: str | None
    cache_hit: bool
    provider_final: str | None
    attempt_count: int
    guard_verdict: str | None
    question_sha256: str | None
    question_char_len: int | None
    sql_fingerprint: str | None
    llm_call_count: int
    cost_usd: float


class LlmCallDetail(BaseModel):
    span_id: str
    attempt_seq: int
    provider: str
    model: str
    operation: str | None
    started_at: datetime
    duration_ms: int | None
    input_tokens: int | None
    output_tokens: int | None
    finish_reason: str | None
    status: str
    error_type: str | None
    cost_usd: float | None


class EvaluationDetail(BaseModel):
    eval_version: str
    sql_parseable: bool | None
    sql_dialect_valid: bool | None
    is_write_statement: bool | None
    tables_referenced: list[str] | None
    scored_at: datetime


class TraceDetail(TraceSummary):
    """A single trace with its children."""

    service_name: str
    environment: str
    ended_at: datetime | None
    root_span_id: str | None
    semconv_version: str | None
    llm_calls: list[LlmCallDetail]
    evaluations: list[EvaluationDetail]
