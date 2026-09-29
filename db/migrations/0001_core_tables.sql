-- One row per traced QueryGuard request.
CREATE TABLE query_events (
    trace_id          text PRIMARY KEY,
    root_span_id      text,
    service_name      text        NOT NULL,
    environment       text        NOT NULL DEFAULT 'local',

    started_at        timestamptz NOT NULL,
    ended_at          timestamptz,
    duration_ms       integer,

    status            text        NOT NULL,
    error_type        text,

    cache_hit         boolean     NOT NULL DEFAULT false,
    provider_final    text,
    attempt_count     smallint    NOT NULL DEFAULT 0,
    guard_verdict     text,

    -- Privacy: hash and shape by default, raw text only when opted in.
    question_sha256   text,
    question_char_len integer,
    question_text     text,
    sql_fingerprint   text,
    sql_text          text,

    semconv_version   text,
    ingested_at       timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT query_events_status_chk CHECK (status IN ('ok', 'error'))
);

-- One row per LLM call. A single request can produce several
-- (retries of the same provider, then a fallback to another).
-- No foreign key on trace_id on purpose: child spans often arrive
-- before the root span they belong to.
CREATE TABLE llm_calls (
    span_id                text PRIMARY KEY,
    trace_id               text        NOT NULL,
    attempt_seq            smallint    NOT NULL DEFAULT 1,

    provider               text        NOT NULL,
    model                  text        NOT NULL,
    operation              text,

    started_at             timestamptz NOT NULL,
    duration_ms            integer,

    input_tokens           integer,
    output_tokens          integer,
    finish_reason          text,

    status                 text        NOT NULL,
    error_type             text,

    cost_usd               numeric(12, 6),
    pricing_effective_from timestamptz,

    semconv_version        text,
    ingested_at            timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT llm_calls_status_chk CHECK (status IN ('ok', 'error'))
);
