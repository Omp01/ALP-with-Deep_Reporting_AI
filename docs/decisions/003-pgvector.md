# ADR-003: pgvector for Semantic Search

## Status
Accepted

## Context
Content ingestion produces text embeddings for semantic similarity search (finding related content, competency matching). A vector storage solution is needed.

## Decision
Use pgvector extension within PostgreSQL rather than a separate vector database.

## Alternatives Considered
- **Pinecone** — managed, highly optimized, but adds external dependency and cost
- **Weaviate** — self-hosted, feature-rich, but adds operational complexity
- **Chroma** — lightweight, but lacks production maturity
- **FAISS (in-memory)** — fast, but doesn't persist and doesn't scale

## Why Selected
1. Eliminates need for a separate infrastructure component
2. 384-dimensional embeddings (MiniLM) are well within pgvector's performance capabilities
3. Embeddings can be queried alongside relational data in a single query
4. Simplifies backup and disaster recovery

## Trade-offs
- Performance degrades with very large vector collections (>10M)
- Fewer specialized vector search features than dedicated solutions

## Future Migration Path
- Extract embeddings to Pinecone/Weaviate if search latency becomes an issue
