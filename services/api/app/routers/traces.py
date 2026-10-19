from datetime import datetime

from fastapi import APIRouter, HTTPException, Path, Query, Request

from ..models import EvaluationDetail, LlmCallDetail, TraceDetail, TraceSummary

router = APIRouter(prefix="/traces", tags=["traces"])

# Columns shared by the list and detail responses.
SUMMARY_COLUMNS = """
    e.trace_id, e.started_at, e.duration_ms, e.status, e.error_type,
    e.cache_hit, e.provider_final, e.attempt_count, e.guard_verdict,
    e.question_sha256, e.question_char_len, e.sql_fingerprint
"""


def _summary_kwargs(row: dict) -> dict:
    return {
        "trace_id": row["trace_id"],
        "started_at": row["started_at"],
        "duration_ms": row["duration_ms"],
        "status": row["status"],
        "error_type": row["error_type"],
        "cache_hit": row["cache_hit"],
        "provider_final": row["provider_final"],
        "attempt_count": row["attempt_count"],
        "guard_verdict": row["guard_verdict"],
        "question_sha256": row["question_sha256"],
        "question_char_len": row["question_char_len"],
        "sql_fingerprint": row["sql_fingerprint"],
        "llm_call_count": row["llm_call_count"],
        "cost_usd": float(row["cost_usd"] or 0),
    }


@router.get(
    "",
    response_model=list[TraceSummary],
    summary="List recent traces",
    description=(
        "Newest first. Use `before` with the `started_at` of the last row you "
        "saw to page backwards without an OFFSET scan."
    ),
)
async def list_traces(
    request: Request,
    hours: int = Query(24, ge=1, le=24 * 90),
    limit: int = Query(50, ge=1, le=500),
    before: datetime | None = Query(
        None, description="Return only traces started strictly before this timestamp."
    ),
    status: str | None = Query(None, pattern="^(ok|error)$"),
    provider: str | None = Query(None, description="Filter on provider_final."),
    cache_hit: bool | None = Query(None),
) -> list[TraceSummary]:
    where = ["e.started_at >= now() - make_interval(hours => %(hours)s)"]
    params: dict = {"hours": hours, "limit": limit}

    if before is not None:
        where.append("e.started_at < %(before)s")
        params["before"] = before
    if status is not None:
        where.append("e.status = %(status)s")
        params["status"] = status
    if provider is not None:
        where.append("e.provider_final = %(provider)s")
        params["provider"] = provider
    if cache_hit is not None:
        where.append("e.cache_hit = %(cache_hit)s")
        params["cache_hit"] = cache_hit

    sql = f"""
        SELECT {SUMMARY_COLUMNS},
               coalesce(c.call_count, 0) AS llm_call_count,
               coalesce(c.cost, 0)       AS cost_usd
        FROM query_events e
        LEFT JOIN (
            SELECT trace_id,
                   count(*)                   AS call_count,
                   coalesce(sum(cost_usd), 0) AS cost
            FROM llm_calls
            GROUP BY trace_id
        ) c ON c.trace_id = e.trace_id
        WHERE {' AND '.join(where)}
        ORDER BY e.started_at DESC
        LIMIT %(limit)s
    """

    async with request.app.state.pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, params)
            rows = await cur.fetchall()

    return [TraceSummary(**_summary_kwargs(r)) for r in rows]


@router.get(
    "/{trace_id}",
    response_model=TraceDetail,
    summary="One trace with its LLM calls and evaluations",
    responses={404: {"description": "No trace with that id."}},
)
async def get_trace(
    request: Request,
    trace_id: str = Path(min_length=1, max_length=64),
) -> TraceDetail:
    event_sql = f"""
        SELECT {SUMMARY_COLUMNS},
               e.service_name, e.environment, e.ended_at,
               e.root_span_id, e.semconv_version,
               coalesce(c.call_count, 0) AS llm_call_count,
               coalesce(c.cost, 0)       AS cost_usd
        FROM query_events e
        LEFT JOIN (
            SELECT trace_id,
                   count(*)                   AS call_count,
                   coalesce(sum(cost_usd), 0) AS cost
            FROM llm_calls
            WHERE trace_id = %(trace_id)s
            GROUP BY trace_id
        ) c ON c.trace_id = e.trace_id
        WHERE e.trace_id = %(trace_id)s
    """
    calls_sql = """
        SELECT span_id, attempt_seq, provider, model, operation,
               started_at, duration_ms, input_tokens, output_tokens,
               finish_reason, status, error_type, cost_usd
        FROM llm_calls
        WHERE trace_id = %(trace_id)s
        ORDER BY attempt_seq, started_at
    """
    evals_sql = """
        SELECT eval_version, sql_parseable, sql_dialect_valid,
               is_write_statement, tables_referenced, scored_at
        FROM evaluations
        WHERE trace_id = %(trace_id)s
        ORDER BY eval_version
    """

    params = {"trace_id": trace_id}
    async with request.app.state.pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(event_sql, params)
            event = await cur.fetchone()
            if event is None:
                raise HTTPException(status_code=404, detail="trace not found")

            await cur.execute(calls_sql, params)
            calls = await cur.fetchall()

            await cur.execute(evals_sql, params)
            evals = await cur.fetchall()

    return TraceDetail(
        **_summary_kwargs(event),
        service_name=event["service_name"],
        environment=event["environment"],
        ended_at=event["ended_at"],
        root_span_id=event["root_span_id"],
        semconv_version=event["semconv_version"],
        llm_calls=[
            LlmCallDetail(
                span_id=c["span_id"],
                attempt_seq=c["attempt_seq"],
                provider=c["provider"],
                model=c["model"],
                operation=c["operation"],
                started_at=c["started_at"],
                duration_ms=c["duration_ms"],
                input_tokens=c["input_tokens"],
                output_tokens=c["output_tokens"],
                finish_reason=c["finish_reason"],
                status=c["status"],
                error_type=c["error_type"],
                cost_usd=float(c["cost_usd"]) if c["cost_usd"] is not None else None,
            )
            for c in calls
        ],
        evaluations=[
            EvaluationDetail(
                eval_version=v["eval_version"],
                sql_parseable=v["sql_parseable"],
                sql_dialect_valid=v["sql_dialect_valid"],
                is_write_statement=v["is_write_statement"],
                tables_referenced=v["tables_referenced"],
                scored_at=v["scored_at"],
            )
            for v in evals
        ],
    )
