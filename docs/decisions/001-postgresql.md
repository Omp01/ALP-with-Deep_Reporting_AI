# ADR-001: PostgreSQL as Primary Database

## Status
Accepted

## Context
The Adaptive LMS requires a relational database for structured data (users, courses, events), vector storage for semantic search (content embeddings), and ACID transactions for data integrity.

## Decision
Use PostgreSQL 16 with the pgvector extension as the single primary database for all services.

## Alternatives Considered
- **MongoDB** — flexible schema, but relational data (users, courses, RBAC) maps poorly to document model
- **PostgreSQL + separate vector DB (Pinecone/Weaviate)** — better vector search, but adds operational complexity
- **MySQL** — lacks native vector support

## Why Selected
1. pgvector provides sufficient vector similarity search for our embedding dimensions (384-dim)
2. Single database simplifies deployment, backup, and operational management
3. PostgreSQL's JSONB columns handle semi-structured data (metadata, error distributions)
4. Excellent async driver support (asyncpg) for FastAPI
5. Mature ecosystem with SQLAlchemy, Alembic

## Trade-offs
- pgvector is less performant than dedicated vector databases at scale (>10M vectors)
- Single database creates a shared dependency across services

## Future Migration Path
- If vector search becomes a bottleneck: migrate embeddings to a dedicated vector database
- If service isolation is needed: implement database-per-service with shared PostgreSQL instance and per-service schemas
