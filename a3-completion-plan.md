# A3 Completion Plan — Schema and Models

## Top-Level Overview

A3 is largely done. The SQLAlchemy models, async DB layer, pydantic-settings config, raw
SQL schema, Alembic env.py, and a smoke-test script are all written and consistent with
each other. Three gaps remain before the A3 done-when criterion is met:

1. **`alembic.ini` is missing** — `alembic` cannot run without it.
2. **`db/init.sql` path mismatch** — `docker-compose.yml` mounts `./db/init.sql` but the
   file lives at `api/db/init.sql`; the schema never gets applied on first boot.
3. **`DATABASE_URL` is absent from `.env.example`** — `config.py` requires it, so any
   developer cloning the repo gets an immediate startup failure with no hint about the
   fix.
4. **Baseline Alembic migration is missing** — `alembic/versions/` is empty; the
   done-when criterion for A3 calls for `alembic init`, baseline migration.

The done-when criterion is: *"a script writes a `scripts` row and reads it back through
the ORM inside the container."* Once the path mismatch is fixed and `alembic.ini` +
baseline migration are created, `verify_a3.py` can be run against the Docker container to
confirm this passes.

---

## Sub-Task 1 — Fix the `db/init.sql` path mismatch

**Intent**
`docker-compose.yml` mounts `./db/init.sql` into the Postgres container's init directory.
The actual file is at `api/db/init.sql`. Until this is corrected, `docker compose up` will
start Postgres with no schema — every table will be missing and the API will crash on
first use.

**Expected Outcomes**
- `./db/init.sql` exists at the repo root level and its content matches `api/db/init.sql`.
- `docker-compose.yml` mount path is consistent with the file location.
- Running `docker compose up db` on a clean volume bootstraps all tables and indexes.

**Todo List**
1. Create the `db/` directory at the repo root.
2. Move `api/db/init.sql` → `db/init.sql` (the compose file is correct; the file is in
   the wrong place).
3. Delete the now-empty `api/db/` directory.

**Relevant Context**
- [`docker-compose.yml`](docker-compose.yml:23) — `./db/init.sql:/docker-entrypoint-initdb.d/init.sql:ro`
- [`api/db/init.sql`](api/db/init.sql) — the existing SQL schema

**Status** — `[x] done`

---

## Sub-Task 2 — Add `DATABASE_URL` to `.env.example`

**Intent**
`config.py` has `database_url: str` as a required field. Nothing in `.env.example` mentions
it. Any developer (or judge) who clones the repo and copies `.env.example` to `.env` will
get a hard startup crash with a cryptic pydantic-settings error rather than a clear "set
DATABASE_URL" message.

**Expected Outcomes**
- `.env.example` contains a `DATABASE_URL` entry with the local-compose default value
  pre-filled as a comment so it works with `docker compose up` out of the box.

**Todo List**
1. Add `DATABASE_URL=postgresql+asyncpg://clearance:clearance@localhost:5432/clearance`
   to `.env.example` under a `# --- Database` section header.

**Relevant Context**
- [`api/app/config.py`](api/app/config.py) — `database_url` is a required setting
- [`.env.example`](.env.example) — currently missing `DATABASE_URL`
- [`docker-compose.yml`](docker-compose.yml:41) — container uses
  `postgresql+asyncpg://clearance:clearance@db:5432/clearance`

**Status** — `[x] done`

---

## Sub-Task 3 — Create `alembic.ini` and the baseline migration

**Intent**
`alembic/env.py` is wired correctly (async engine, imports models, reads `DATABASE_URL`
from settings) but `alembic.ini` — the file that tells the `alembic` CLI where `env.py`
lives, where to write migration files, and which logging config to use — does not exist.
Without it, every `alembic` command fails immediately. A baseline (empty) migration must
also be created so future schema changes have a starting point.

**Expected Outcomes**
- `alembic.ini` exists at the repo root, pointing `script_location = alembic` and
  setting `sqlalchemy.url` to a placeholder (the real URL comes from env.py, not ini).
- Running `python -m alembic current` against a running Postgres instance succeeds.
- `alembic/versions/` contains exactly one migration file — the baseline — with no
  upgrade/downgrade ops (it represents the schema already created by `db/init.sql`).
- Running `python -m alembic upgrade head` against a fresh DB that already has the schema
  is a no-op (baseline migration marks it as current).

**Todo List**
1. Create `alembic.ini` at the repo root using the standard Alembic template; set
   `script_location = alembic` and `sqlalchemy.url = ` (empty — overridden by env.py).
2. Generate a baseline migration:
   `python -m alembic revision -m "baseline"` — then verify the file appears in
   `alembic/versions/`.
3. Confirm `env.py` is already correct (it is — verified in investigation; no changes
   needed there).

**Relevant Context**
- [`alembic/env.py`](alembic/env.py) — already correct; reads URL from settings
- [`alembic/versions/`](alembic/versions/) — currently empty
- `alembic.ini` — does not yet exist

**Status** — `[x] done`

---

## Sub-Task 4 — Verify A3 done-when criterion inside Docker

**Intent**
The A3 done-when is: *"a script writes a `scripts` row and reads it back through the ORM
inside the container."* `verify_a3.py` already does exactly this, but it has never been
confirmed to pass against the running Docker stack after the path-mismatch fix.

**Expected Outcomes**
- `docker compose up db -d` starts cleanly.
- `python api/scripts/verify_a3.py` prints `✓ A3 smoke-test passed` with no errors.
- The test row is cleaned up (script already handles this).

**Todo List**
1. After Sub-Tasks 1–3 are complete, start the `db` service: `docker compose up db -d`.
2. Set `DATABASE_URL=postgresql+asyncpg://clearance:clearance@localhost:5432/clearance`
   in `.env`.
3. Run `python api/scripts/verify_a3.py` from the repo root.
4. Confirm the output ends with `✓ A3 smoke-test passed`.
5. Mark A3 done in `implementation-checklist.md`.

**Relevant Context**
- [`api/scripts/verify_a3.py`](api/scripts/verify_a3.py) — the smoke test
- [`api/app/db.py`](api/app/db.py:25) — `init_db()` called by the script; creates tables
  if they don't exist

**Status** — `[x] done`
