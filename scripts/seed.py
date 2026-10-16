#!/usr/bin/env python3
"""
Generate synthetic LogWatch telemetry for dashboard development.

Every row is written with environment='synthetic' so it can be
identified and removed. The scenario mix below is INVENTED for the
purpose of building and testing dashboards. It is not a measurement
of QueryGuard's real behaviour; real proportions are measured in
Phase 6 against live traffic.
"""
import argparse
import hashlib
import os
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

import psycopg
from dotenv import load_dotenv

ENVIRONMENT = "synthetic"
SERVICE_NAME = "queryguard"
SEMCONV_VERSION = "1.36.0"
EVAL_VERSION = "synthetic-v0"

GEMINI = ("gcp.gemini", "gemini-3.5-flash")
NIM = ("nvidia.nim", "meta/llama-3.3-70b-instruct")

# scenario -> relative weight (invented; see module docstring)
SCENARIOS = {
    "cache_hit": 25,
    "gemini_ok": 55,
    "gemini_retry_ok": 8,
    "nim_fallback": 9,
    "total_failure": 3,
}
# during a bad window, failures dominate
BURST_SCENARIOS = {
    "cache_hit": 10,
    "gemini_ok": 15,
    "gemini_retry_ok": 20,
    "nim_fallback": 35,
    "total_failure": 20,
}

# relative traffic by hour of day (UTC), to give panels a visible shape
HOUR_WEIGHTS = [
    2, 1, 1, 1, 1, 2, 4, 7, 10, 13, 15, 16,
    15, 14, 15, 16, 14, 11, 9, 7, 6, 5, 4, 3,
]

QUESTION_TEMPLATES = [
    "how many orders were placed last month",
    "show me the top customers by revenue",
    "what is the average order value this quarter",
    "list all products that are out of stock",
    "which region had the highest sales growth",
    "total refunds issued in the past week",
    "count active subscriptions by plan",
    "revenue breakdown by payment method",
]

SQL_FINGERPRINTS = [
    "SELECT count(?) FROM T1 WHERE C2 >= ?",
    "SELECT C1, sum(C4) FROM T2 GROUP BY C1 ORDER BY ? DESC LIMIT ?",
    "SELECT avg(C3) FROM T1 WHERE C5 BETWEEN ? AND ?",
    "SELECT C1 FROM T3 WHERE C2 = ?",
    "SELECT C1, C2 FROM T2 JOIN T4 ON T2.C1 = T4.C1 WHERE C6 > ?",
]

ERROR_TYPES = ["timeout", "rate_limited", "upstream_5xx", "invalid_response"]


def hex_id(rng, bits):
    return f"{rng.getrandbits(bits):0{bits // 4}x}"


def lognormal_ms(rng, median_ms, sigma):
    """Latency with a realistic long right tail."""
    import math
    return max(1, int(rng.lognormvariate(math.log(median_ms), sigma)))


def load_pricing(conn):
    with conn.cursor() as cur:
        cur.execute("""
            SELECT provider, model, input_usd_per_1k,
                   output_usd_per_1k, effective_from
            FROM model_pricing
        """)
        return cur.fetchall()


def price_for(pricing, provider, model, at):
    best = None
    for row in pricing:
        if row[0] == provider and row[1] == model and row[4] <= at:
            if best is None or row[4] > best[4]:
                best = row
    return best


def cost_of(pricing, provider, model, at, in_tok, out_tok):
    row = price_for(pricing, provider, model, at)
    if row is None or in_tok is None:
        return None, None
    cost = (Decimal(in_tok) / 1000) * row[2] + (Decimal(out_tok) / 1000) * row[3]
    return cost.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP), row[4]


def pick_timestamp(rng, now, days):
    day_offset = rng.randrange(days)
    hour = rng.choices(range(24), weights=HOUR_WEIGHTS, k=1)[0]
    base = now - timedelta(days=day_offset)
    return base.replace(
        hour=hour,
        minute=rng.randrange(60),
        second=rng.randrange(60),
        microsecond=rng.randrange(1_000_000),
    )


def make_bad_windows(rng, now, days, count=6):
    windows = []
    for _ in range(count):
        start = now - timedelta(
            days=rng.randrange(days),
            hours=rng.randrange(24),
            minutes=rng.randrange(60),
        )
        windows.append((start, start + timedelta(minutes=rng.randrange(20, 60))))
    return windows


def in_bad_window(ts, windows):
    return any(start <= ts <= end for start, end in windows)


def build_calls(rng, scenario, started_at, pricing):
    """Return the llm_calls rows for one trace, as dicts."""
    calls = []
    cursor = started_at

    def one(provider_model, status, seq):
        nonlocal cursor
        provider, model = provider_model
        dur = lognormal_ms(rng, 900 if status == "ok" else 1800, 0.45)
        if status == "ok":
            in_tok = rng.randrange(350, 1800)
            out_tok = rng.randrange(40, 320)
            finish = "stop"
            err = None
        else:
            in_tok = out_tok = None
            finish = None
            err = rng.choice(ERROR_TYPES)
        cost, eff = cost_of(pricing, provider, model, cursor, in_tok, out_tok)
        row = {
            "span_id": hex_id(rng, 64),
            "attempt_seq": seq,
            "provider": provider,
            "model": model,
            "operation": "chat",
            "started_at": cursor,
            "duration_ms": dur,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "finish_reason": finish,
            "status": status,
            "error_type": err,
            "cost_usd": cost,
            "pricing_effective_from": eff,
        }
        cursor = cursor + timedelta(milliseconds=dur + rng.randrange(5, 40))
        calls.append(row)

    if scenario == "cache_hit":
        pass
    elif scenario == "gemini_ok":
        one(GEMINI, "ok", 1)
    elif scenario == "gemini_retry_ok":
        for seq in range(1, rng.randrange(2, 4)):
            one(GEMINI, "error", seq)
        one(GEMINI, "ok", len(calls) + 1)
    elif scenario == "nim_fallback":
        for seq in range(1, rng.randrange(2, 4)):
            one(GEMINI, "error", seq)
        one(NIM, "ok", len(calls) + 1)
    elif scenario == "total_failure":
        for seq in range(1, 4):
            one(GEMINI, "error", seq)
        one(NIM, "error", 4)

    return calls


def build_trace(rng, now, days, windows, pricing):
    started_at = pick_timestamp(rng, now, days)
    weights = BURST_SCENARIOS if in_bad_window(started_at, windows) else SCENARIOS
    scenario = rng.choices(list(weights), weights=list(weights.values()), k=1)[0]

    trace_id = hex_id(rng, 128)
    root_span_id = hex_id(rng, 64)
    calls = build_calls(rng, scenario, started_at, pricing)

    question = rng.choice(QUESTION_TEMPLATES)
    cache_hit = scenario == "cache_hit"
    failed = scenario == "total_failure"

    if cache_hit:
        duration_ms = rng.randrange(14, 41)
    else:
        overhead = rng.randrange(25, 90)
        duration_ms = sum(c["duration_ms"] + 20 for c in calls) + overhead

    successful = [c for c in calls if c["status"] == "ok"]
    provider_final = successful[-1]["provider"] if successful else (
        "cache" if cache_hit else None
    )

    is_write = (not failed) and rng.random() < 0.02
    guard_verdict = "blocked_write" if is_write else ("allowed" if not failed else None)

    event = {
        "trace_id": trace_id,
        "root_span_id": root_span_id,
        "service_name": SERVICE_NAME,
        "environment": ENVIRONMENT,
        "started_at": started_at,
        "ended_at": started_at + timedelta(milliseconds=duration_ms),
        "duration_ms": duration_ms,
        "status": "error" if failed else "ok",
        "error_type": calls[-1]["error_type"] if failed else None,
        "cache_hit": cache_hit,
        "provider_final": provider_final,
        "attempt_count": len(calls),
        "guard_verdict": guard_verdict,
        "question_sha256": hashlib.sha256(question.encode()).hexdigest(),
        "question_char_len": len(question),
        "question_text": None,      # capture disabled by default
        "sql_fingerprint": None if failed else rng.choice(SQL_FINGERPRINTS),
        "sql_text": None,           # capture disabled by default
        "semconv_version": SEMCONV_VERSION,
    }

    for c in calls:
        c["trace_id"] = trace_id
        c["semconv_version"] = SEMCONV_VERSION

    if failed:
        evaluation = None
    else:
        parseable = rng.random() < 0.98
        evaluation = {
            "trace_id": trace_id,
            "eval_version": EVAL_VERSION,
            "sql_parseable": parseable,
            "sql_dialect_valid": parseable and rng.random() < 0.95,
            "is_write_statement": is_write,
            "tables_referenced": rng.sample(
                ["T1", "T2", "T3", "T4", "T5"], rng.randrange(1, 3)
            ),
        }

    return event, calls, evaluation


EVENT_SQL = """
INSERT INTO query_events (
    trace_id, root_span_id, service_name, environment,
    started_at, ended_at, duration_ms, status, error_type,
    cache_hit, provider_final, attempt_count, guard_verdict,
    question_sha256, question_char_len, question_text,
    sql_fingerprint, sql_text, semconv_version
) VALUES (
    %(trace_id)s, %(root_span_id)s, %(service_name)s, %(environment)s,
    %(started_at)s, %(ended_at)s, %(duration_ms)s, %(status)s, %(error_type)s,
    %(cache_hit)s, %(provider_final)s, %(attempt_count)s, %(guard_verdict)s,
    %(question_sha256)s, %(question_char_len)s, %(question_text)s,
    %(sql_fingerprint)s, %(sql_text)s, %(semconv_version)s
) ON CONFLICT (trace_id) DO NOTHING
"""

CALL_SQL = """
INSERT INTO llm_calls (
    span_id, trace_id, attempt_seq, provider, model, operation,
    started_at, duration_ms, input_tokens, output_tokens,
    finish_reason, status, error_type, cost_usd,
    pricing_effective_from, semconv_version
) VALUES (
    %(span_id)s, %(trace_id)s, %(attempt_seq)s, %(provider)s, %(model)s, %(operation)s,
    %(started_at)s, %(duration_ms)s, %(input_tokens)s, %(output_tokens)s,
    %(finish_reason)s, %(status)s, %(error_type)s, %(cost_usd)s,
    %(pricing_effective_from)s, %(semconv_version)s
) ON CONFLICT (span_id) DO NOTHING
"""

EVAL_SQL = """
INSERT INTO evaluations (
    trace_id, eval_version, sql_parseable, sql_dialect_valid,
    is_write_statement, tables_referenced
) VALUES (
    %(trace_id)s, %(eval_version)s, %(sql_parseable)s, %(sql_dialect_valid)s,
    %(is_write_statement)s, %(tables_referenced)s
) ON CONFLICT (trace_id, eval_version) DO NOTHING
"""


def purge(conn):
    with conn.cursor() as cur:
        # llm_calls has no FK on purpose, so it must be deleted explicitly
        # before the parent rows disappear.
        cur.execute("""
            DELETE FROM llm_calls WHERE trace_id IN (
                SELECT trace_id FROM query_events WHERE environment = %s
            )
        """, (ENVIRONMENT,))
        calls = cur.rowcount
        # evaluations go automatically via ON DELETE CASCADE
        cur.execute("DELETE FROM query_events WHERE environment = %s", (ENVIRONMENT,))
        return cur.rowcount, calls


def main():
    ap = argparse.ArgumentParser(description="Generate synthetic LogWatch telemetry.")
    ap.add_argument("--count", type=int, default=5000, help="traces to generate")
    ap.add_argument("--days", type=int, default=7, help="spread over the last N days")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed for reproducibility")
    ap.add_argument("--purge", action="store_true", help="delete synthetic rows first")
    ap.add_argument("--purge-only", action="store_true", help="delete and exit")
    args = ap.parse_args()

    load_dotenv()
    dsn = (
        f"postgresql://{os.environ['POSTGRES_USER']}:{os.environ['POSTGRES_PASSWORD']}"
        f"@localhost:5433/{os.environ['POSTGRES_DB']}"
    )

    rng = random.Random(args.seed)
    now = datetime.now(timezone.utc)

    with psycopg.connect(dsn) as conn:
        if args.purge or args.purge_only:
            ev, ca = purge(conn)
            conn.commit()
            print(f"purged {ev} synthetic query_events and {ca} llm_calls")
            if args.purge_only:
                return

        pricing = load_pricing(conn)
        if not pricing:
            raise SystemExit("model_pricing is empty - run 'make migrate' first")

        windows = make_bad_windows(rng, now, args.days)

        events, calls, evals = [], [], []
        for _ in range(args.count):
            e, c, v = build_trace(rng, now, args.days, windows, pricing)
            events.append(e)
            calls.extend(c)
            if v:
                evals.append(v)

        with conn.cursor() as cur:
            cur.executemany(EVENT_SQL, events)
            cur.executemany(CALL_SQL, calls)
            cur.executemany(EVAL_SQL, evals)
        conn.commit()

    print(f"inserted {len(events)} traces, {len(calls)} llm_calls, "
          f"{len(evals)} evaluations (seed={args.seed}, days={args.days})")


if __name__ == "__main__":
    main()
