"""A3 smoke-test — write a scripts row and read it back through the ORM.

Requirements:
  - DATABASE_URL in .env (or environment) pointing at a running Postgres instance.
  - The clearance DB must exist and the schema must be initialised.

Quick start with a bare Docker container (no compose needed):

    docker run -d --name pg-verify \
        -e POSTGRES_USER=clearance \
        -e POSTGRES_PASSWORD=clearance \
        -e POSTGRES_DB=clearance \
        -p 5432:5432 postgres:16

    # Then set DATABASE_URL in .env:
    # DATABASE_URL=postgresql+asyncpg://clearance:clearance@localhost:5432/clearance

    python api/scripts/verify_a3.py

    docker rm -f pg-verify  # cleanup

The script calls init_db() first, so it is safe to run against a fresh database
that has not had init.sql or alembic applied yet.
"""

import asyncio
import sys
import uuid
from pathlib import Path

# Make sure repo root is on the path when run as a script
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from sqlalchemy import select  # noqa: E402

from api.app.db import AsyncSessionLocal, init_db  # noqa: E402
from api.app.models import Script  # noqa: E402


async def main() -> None:
    print("Initialising schema (no-op if tables already exist)…")
    await init_db()

    async with AsyncSessionLocal() as session:
        # ── INSERT ─────────────────────────────────────────────────────────
        test_id = uuid.uuid4()
        script = Script(
            id=test_id,
            title="VERIFY A3 TEST SCRIPT",
            filename="verify_a3.pdf",
            storage_path=f"scripts/{test_id}/original.pdf",
            sha256="deadbeef" * 8,  # 64-char hex placeholder
            source_format="pdf",
            page_count=10,
            scene_count=3,
            parse_warnings=[],
        )
        session.add(script)
        await session.commit()
        print(f"Inserted  Script id={test_id}")

        # ── READ BACK ──────────────────────────────────────────────────────
        result = await session.execute(select(Script).where(Script.id == test_id))
        row = result.scalar_one()
        print(f"Read back Script id={row.id}")
        print(f"           title={row.title!r}")
        print(f"           page_count={row.page_count}, scene_count={row.scene_count}")
        print(f"           parse_warnings={row.parse_warnings!r}")
        assert row.title == "VERIFY A3 TEST SCRIPT", "title mismatch"
        assert row.scene_count == 3, "scene_count mismatch"

        # ── CLEANUP ────────────────────────────────────────────────────────
        await session.delete(row)
        await session.commit()
        print("Deleted   test row — database is clean")

    print("\nPASSED: A3 smoke-test passed")


if __name__ == "__main__":
    asyncio.run(main())
