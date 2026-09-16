# ADR-002: Redis Streams for Async Event Processing

## Status
Accepted

## Context
Learning events need asynchronous processing: competency updates, risk scanning, and digest generation should not block the API response to the learner.

## Decision
Use Redis Streams as the event bus for async processing between the API Service and background workers.

## Alternatives Considered
- **Apache Kafka** — industry standard for event streaming, but significant operational overhead
- **RabbitMQ** — mature message broker, but adds another infrastructure component
- **PostgreSQL LISTEN/NOTIFY** — simple, but lacks consumer groups and replay
- **Celery** — task queue, but events are better modeled as streams than tasks

## Why Selected
1. Redis is already required for caching — no additional infrastructure
2. Redis Streams provide consumer groups, message acknowledgment, and replay
3. Simpler operations than Kafka for the current scale
4. Learning events are persisted to PostgreSQL first, so Redis Streams durability is not critical
5. Good Python client support via redis-py

## Trade-offs
- Redis Streams lack Kafka's durability guarantees (events survive Redis restart via RDB/AOF, but not as robustly as Kafka)
- Limited to single-node Redis in development (Redis Cluster for production)

## Future Migration Path
- If event volume exceeds Redis capacity: migrate to Apache Kafka with minimal code changes (consumer interface is abstracted)
