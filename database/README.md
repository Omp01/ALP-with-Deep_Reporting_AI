# Database

This directory contains:

- **migrations/** — Alembic database migrations (created in Phase 2)
- **seeds/** — Seed data and demo data generators (created in Phase 2)

## Running Migrations

```bash
# Inside the API container
alembic upgrade head
```

## Seeding Data

```bash
# From the project root
python scripts/seed.py
```

## Schema

See [docs/DATA_MODEL.md](../docs/DATA_MODEL.md) for the complete database schema documentation.
