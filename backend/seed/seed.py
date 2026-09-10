"""Deterministic local seed.

Produces a clean demo database from a script rather than from whatever state a
laptop happens to be in (docs/plan/PHASES.md, P0 and P4).

Never uses real victim or NHAA data. Every person, place and incident here is
fictional.

Determinism: every primary key is a fixed UUID5 derived from a project
namespace, so re-running the seed produces byte-identical rows and a rehearsal
can be repeated exactly. Password hashes are the one exception -- Argon2 salts
per call by design -- so hashes differ between runs while the credentials do not.

Credentials are never committed. The seed password comes from SEED_PASSWORD in
the environment, or is generated and printed once for a local demo.
"""

import argparse
import asyncio
import os
import secrets
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import delete, select  # noqa: E402

from backend.app.core.config import get_settings  # noqa: E402
from backend.app.core.db import SessionLocal  # noqa: E402
from backend.app.core.security import hash_password  # noqa: E402
from backend.app.models import PolicyChunk, User  # noqa: E402

#: Fixed namespace so ids are stable across machines and runs.
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "sahay-ai.local.seed")


def sid(kind: str, key: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{kind}:{key}"))


#: Fictional helpline staff. No real person.
USERS = (
    {"username": "exec1", "role": "executive", "display_name": "Executive One"},
    {"username": "exec2", "role": "executive", "display_name": "Executive Two"},
    {"username": "sup1", "role": "supervisor", "display_name": "Supervisor One"},
)

#: Minimal local retrieval corpus so the keyword retriever has something to
#: return. These are neutral process descriptions written for this project.
#: They are NOT quotations from any statute, and they carry no citation to one:
#: an official policy corpus is EXT-108 and still PROPOSED.
POLICY_CHUNKS = (
    {
        "key": "process-complaint",
        "source": "project-placeholder",
        "citation": "PLACEHOLDER-01",
        "text": "A complaint recorded through the helpline is reviewed by a helpline "
                "executive before any action is assigned.",
        "keywords": ["complaint", "review", "executive", "record"],
    },
    {
        "key": "process-escalation",
        "source": "project-placeholder",
        "citation": "PLACEHOLDER-02",
        "text": "A case marked for immediate attention is placed at the top of the "
                "queue and requires acknowledgement by a named officer.",
        "keywords": ["escalation", "queue", "acknowledgement", "officer"],
    },
    {
        "key": "process-handoff",
        "source": "project-placeholder",
        "citation": "PLACEHOLDER-03",
        "text": "A request to speak with a person is honoured at any point and does "
                "not depend on the state of the intake.",
        "keywords": ["human", "handoff", "request", "person"],
    },
)


async def seed(reset: bool, password: str) -> int:
    settings = get_settings()
    settings.ensure_runtime_dirs()

    async with SessionLocal() as session:
        if reset:
            # Only the rows this script owns. It never drops tables and never
            # touches session, turn, case or audit data.
            await session.execute(delete(PolicyChunk))
            await session.execute(delete(User))
            await session.commit()

        existing = {row[0] for row in (await session.execute(select(User.username))).all()}

        created = []
        for spec in USERS:
            if spec["username"] in existing:
                continue
            session.add(
                User(
                    id=sid("user", spec["username"]),
                    username=spec["username"],
                    password_hash=hash_password(password),
                    role=spec["role"],
                    display_name=spec["display_name"],
                )
            )
            created.append(spec["username"])

        have = {row[0] for row in (await session.execute(select(PolicyChunk.citation))).all()}
        chunks = []
        for spec in POLICY_CHUNKS:
            if spec["citation"] in have:
                continue
            session.add(
                PolicyChunk(
                    id=sid("policy", spec["key"]),
                    source=spec["source"],
                    citation=spec["citation"],
                    text=spec["text"],
                    keywords=spec["keywords"],
                )
            )
            chunks.append(spec["citation"])

        await session.commit()

    print(f"database:       {settings.DATABASE_URL}")
    print(f"users created:  {created or 'none (already present)'}")
    print(f"policy chunks:  {chunks or 'none (already present)'}")
    print("no victim, session, case or assessment data is seeded")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Seed the local SAHAY-AI database")
    parser.add_argument("--reset", action="store_true",
                        help="delete seeded users and policy chunks first")
    args = parser.parse_args(argv)

    password = os.environ.get("SEED_PASSWORD")
    generated = password is None
    if generated:
        password = secrets.token_urlsafe(12)

    code = asyncio.run(seed(args.reset, password))

    if generated:
        print()
        print("Generated a local demo password for every seeded account:")
        print(f"    {password}")
        print("It is not stored anywhere but the password hash. Set SEED_PASSWORD "
              "to choose your own. Never use this on anything but a local demo.")
    return code


if __name__ == "__main__":
    sys.exit(main())
