from fastapi import APIRouter, Query, Request

from ..models import DailyCost, LatencyStats, ProviderStats, Summary

router = APIRouter(prefix="/stats", tags=["stats"])

HOURS = Query(24, ge=1, le=24 * 90, description="Look back this many hours.")


@router.get("/summary", response_model=Summary, summary="Headline numbers")
async def summary(request: Request, hours: int = HOURS) -> Summary:
    sql = """
        WITH ev AS (
            SELECT *
            FROM query_events
            WHERE started_at >= now() - make_interval(hours => %(hours)s)
        ),
        cost AS (
            SELECT coalesce(sum(cost_usd), 0) AS total
            FROM llm_calls
            WHERE started_at >= now() - make_interval(hours => %(hours)s)
        )
        SELECT
            count(*)                                            AS total_requests,
            count(*) FILTER (WHERE cache_hit)                    AS cache_hits,
            count(*) FILTER (WHERE status = 'error')             AS errors,
            count(*) FILTER (WHERE provider_final = 'nvidia.nim') AS fallback_requests,
            count(*) FILTER (WHERE NOT cache_hit)                AS model_backed,
            (SELECT total FROM cost)                             AS total_cost_usd
        FROM ev
    """
    async with request.app.state.pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, {"hours": hours})
            row = await cur.fetchone()

    total = row["total_requests"]
    model_backed = row["model_backed"]

    def pct(numerator: int, denominator: int) -> float | None:
        if not denominator:
            return None
        return round(100.0 * numerator / denominator, 2)

    return Summary(
        window_hours=hours,
        total_requests=total,
        cache_hits=row["cache_hits"],
        cache_hit_rate_pct=pct(row["cache_hits"], total),
        errors=row["errors"],
        error_rate_pct=pct(row["errors"], total),
        fallback_requests=row["fallback_requests"],
        fallback_rate_pct=pct(row["fallback_requests"], model_backed),
        total_cost_usd=float(row["total_cost_usd"]),
    )


@router.get("/latency", response_model=LatencyStats, summary="Latency percentiles")
async def latency(request: Request, hours: int = HOURS) -> LatencyStats:
    sql = """
        SELECT
            count(*)                                                     AS sample_size,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY duration_ms)    AS p50,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)    AS p95,
            percentile_cont(0.99) WITHIN GROUP (ORDER BY duration_ms)    AS p99,
            max(duration_ms)                                             AS max_ms
        FROM query_events
        WHERE started_at >= now() - make_interval(hours => %(hours)s)
          AND NOT cache_hit
    """
    async with request.app.state.pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, {"hours": hours})
            row = await cur.fetchone()

    return LatencyStats(
        window_hours=hours,
        sample_size=row["sample_size"],
        p50_ms=row["p50"],
        p95_ms=row["p95"],
        p99_ms=row["p99"],
        max_ms=row["max_ms"],
    )


@router.get(
    "/providers",
    response_model=list[ProviderStats],
    summary="Per-provider call statistics",
)
async def providers(request: Request, hours: int = HOURS) -> list[ProviderStats]:
    sql = """
        SELECT
            provider,
            model,
            count(*)                                                  AS calls,
            count(*) FILTER (WHERE status = 'ok')                     AS successes,
            count(*) FILTER (WHERE status = 'error')                  AS failures,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY duration_ms) AS p50,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95,
            coalesce(sum(input_tokens), 0)                            AS input_tokens,
            coalesce(sum(output_tokens), 0)                           AS output_tokens,
            coalesce(sum(cost_usd), 0)                                AS cost_usd
        FROM llm_calls
        WHERE started_at >= now() - make_interval(hours => %(hours)s)
        GROUP BY provider, model
        ORDER BY calls DESC
    """
    async with request.app.state.pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, {"hours": hours})
            rows = await cur.fetchall()

    return [
        ProviderStats(
            provider=r["provider"],
            model=r["model"],
            calls=r["calls"],
            successes=r["successes"],
            failures=r["failures"],
            success_rate_pct=round(100.0 * r["successes"] / r["calls"], 2),
            p50_ms=r["p50"],
            p95_ms=r["p95"],
            input_tokens=r["input_tokens"],
            output_tokens=r["output_tokens"],
            cost_usd=float(r["cost_usd"]),
        )
        for r in rows
    ]


@router.get(
    "/cost/daily",
    response_model=list[DailyCost],
    summary="Cost per day per provider",
)
async def daily_cost(
    request: Request,
    days: int = Query(30, ge=1, le=365, description="Look back this many days."),
) -> list[DailyCost]:
    sql = """
        SELECT
            date_trunc('day', started_at)   AS day,
            provider,
            count(*)                        AS calls,
            coalesce(sum(input_tokens), 0)  AS input_tokens,
            coalesce(sum(output_tokens), 0) AS output_tokens,
            coalesce(sum(cost_usd), 0)      AS cost_usd
        FROM llm_calls
        WHERE started_at >= now() - make_interval(days => %(days)s)
        GROUP BY 1, 2
        ORDER BY 1 DESC, 2
    """
    async with request.app.state.pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(sql, {"days": days})
            rows = await cur.fetchall()

    return [
        DailyCost(
            day=r["day"],
            provider=r["provider"],
            calls=r["calls"],
            input_tokens=r["input_tokens"],
            output_tokens=r["output_tokens"],
            cost_usd=float(r["cost_usd"]),
        )
        for r in rows
    ]
