# 2. Kafka's role: decouple the consumer, not the producer

Date: 2026-09-21
Status: Accepted

## Context
QueryGuard must never block on telemetry. The OTel SDK's
BatchSpanProcessor already guarantees this: spans go to a bounded
in-memory queue, export happens on a background thread, and spans
are dropped (not blocked on) when the queue is full.

## Decision
Use Kafka between the OTel Collector and the ingest/evaluation
consumer, for three reasons the SDK cannot provide:
1. Consumer lifecycle decoupling: the consumer can restart or be
   down without losing telemetry.
2. Durable replay: re-score history with a new eval version by
   consuming from an earlier offset under a new consumer group.
3. Backpressure absorption: bursts are absorbed by the log; the
   consumer drains at its own rate.

## Consequences
+ Evaluation logic can change and redeploy freely; history is replayable.
- Adds a stateful component to operate (single broker, RF=1 locally;
  not durable against disk loss; production would need RF=3).
- At-least-once delivery means the consumer must be idempotent.
