# 1. Record architecture decisions

Date: 2026-09-21
Status: Accepted

## Context
LogWatch makes several non-obvious choices (Kafka, OTel Collector,
deterministic evaluation) that I need to justify later.

## Decision
Record each significant decision as a numbered ADR (Nygard format).
ADRs are append-only; changed decisions get a superseding ADR.

## Consequences
Decisions and their trade-offs stay reviewable alongside the code.
Small ongoing cost: ~10 minutes per decision.
