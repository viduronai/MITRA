-- Runs once when the server's Postgres volume is first created (deploy/compose.yml).
-- The schema and the mitra_app role come from the core migrations (alembic upgrade heads).
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
