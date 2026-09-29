-- Why a price is what it is. Needed because not every provider
-- publishes a per-token rate.
ALTER TABLE model_pricing ADD COLUMN pricing_note text;

-- Google publishes per-token rates for Gemini.
INSERT INTO model_pricing
    (provider, model, input_usd_per_1k, output_usd_per_1k,
     effective_from, source_url, pricing_note)
VALUES
    ('gcp.gemini', 'gemini-3.5-flash', 0.000750, 0.004500,
     '2026-05-19T00:00:00Z',
     'https://ai.google.dev/gemini-api/docs/pricing',
     'Published paid-tier text rate: $0.75/M input, $4.50/M output. Verified 2026-09-29.');

-- NVIDIA publishes no per-token rate for the hosted NIM catalog.
-- Recorded as zero deliberately, with the reason, rather than
-- inventing a number or leaving cost NULL and ambiguous.
INSERT INTO model_pricing
    (provider, model, input_usd_per_1k, output_usd_per_1k,
     effective_from, source_url, pricing_note)
VALUES
    ('nvidia.nim', 'meta/llama-3.3-70b-instruct', 0.000000, 0.000000,
     '2026-01-01T00:00:00Z',
     'https://build.nvidia.com/',
     'No public per-token price. Hosted catalog is free for prototyping via the NVIDIA Developer Program (rate limited); production is licensed per GPU, not per token. Zero is a sourced placeholder, not a measured cost. Verified 2026-09-29.');
