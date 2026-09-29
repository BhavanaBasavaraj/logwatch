-- LogWatch's own scoring of a traced request.
-- Composite PK means a trace can be re-scored by a newer evaluator
-- without destroying the previous verdict.
CREATE TABLE evaluations (
    trace_id          text        NOT NULL
                      REFERENCES query_events(trace_id) ON DELETE CASCADE,
    eval_version      text        NOT NULL,

    sql_parseable     boolean,
    sql_dialect_valid boolean,
    is_write_statement boolean,
    tables_referenced text[],

    scored_at         timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (trace_id, eval_version)
);

-- Reference data: what each model costs, with dated rows so that
-- a future price change does not rewrite past costs.
CREATE TABLE model_pricing (
    provider          text        NOT NULL,
    model             text        NOT NULL,
    input_usd_per_1k  numeric(12, 6) NOT NULL,
    output_usd_per_1k numeric(12, 6) NOT NULL,
    effective_from    timestamptz NOT NULL,
    source_url        text,

    PRIMARY KEY (provider, model, effective_from)
);

-- Escape hatch: the original span payload, exactly as received.
-- Lets us recover a field we forgot to extract, without replaying Kafka.
CREATE TABLE spans_raw (
    span_id     text PRIMARY KEY,
    trace_id    text        NOT NULL,
    payload     jsonb       NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now()
);
