-- Every dashboard panel filters by time, so this is the workhorse index.
CREATE INDEX idx_query_events_started_at
    ON query_events (started_at DESC);

-- "Latency by provider over the last N hours" and similar breakdowns.
CREATE INDEX idx_query_events_provider_started_at
    ON query_events (provider_final, started_at DESC);

-- Error-rate panels.
CREATE INDEX idx_query_events_status_started_at
    ON query_events (status, started_at DESC);

-- Joining a request to its LLM calls. No FK here, so no automatic index.
CREATE INDEX idx_llm_calls_trace_id
    ON llm_calls (trace_id);

-- Token and cost panels grouped by provider and model.
CREATE INDEX idx_llm_calls_provider_model_started_at
    ON llm_calls (provider, model, started_at DESC);

-- Looking up the raw payload for a request while debugging.
CREATE INDEX idx_spans_raw_trace_id
    ON spans_raw (trace_id);
