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
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import delete, func, select  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.exc import ArgumentError  # noqa: E402

from backend.app.core.config import REPO_ROOT, get_settings  # noqa: E402
from backend.app.core.security import hash_password  # noqa: E402

#: Fixed namespace so ids are stable across machines and runs.
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "sahay-ai.local.seed")
SAFE_LOCAL_DATABASE_ROOT = (REPO_ROOT / "runtime" / "db").resolve()
SAFE_TEMP_ROOT = Path(tempfile.gettempdir()).resolve()
_SAFE_DATABASE_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})
_UNSAFE_TARGET_MESSAGE = (
    "seed refused: database target is not an approved development/demo database"
)
_REMOTE_CONFIRMATION = "AUTHORIZE_EMPTY_SAHAY_DEMO_SEED"


class UnsafeSeedTarget(ValueError):
    """A fixed-message refusal that never carries the configured DSN."""


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def validate_seed_target(
    database_url: str,
    *,
    app_env: str = "test",
    allow_remote: bool = False,
    project_ref: str = "",
    confirmation: str = "",
) -> str:
    """Return a safe display label or reject before database initialization.

    Normal development databases live under ``runtime/db``. Existing backend
    tests create their databases in a unique ``TemporaryDirectory`` beneath
    the operating-system temp root, so only nested temp paths are accepted.
    """
    try:
        url = make_url(database_url)
    except (ArgumentError, TypeError, ValueError):
        raise UnsafeSeedTarget(_UNSAFE_TARGET_MESSAGE) from None

    if url.get_backend_name() == "postgresql":
        host = (url.host or "").casefold()
        detected_ref = ""
        is_direct = host.startswith("db.") and host.endswith(".supabase.co")
        is_session_pooler = host.endswith(".pooler.supabase.com") and url.port == 5432
        if is_direct:
            detected_ref = host.removeprefix("db.").removesuffix(".supabase.co")
        elif is_session_pooler and url.username and "." in url.username:
            detected_ref = url.username.rsplit(".", 1)[-1]
        if (
            url.drivername != "postgresql+asyncpg"
            or url.port == 6543
            or not (is_direct or is_session_pooler)
            or not detected_ref
            or app_env not in {"development", "demo"}
            or not allow_remote
            or not project_ref
            or not secrets.compare_digest(detected_ref, project_ref.casefold())
            or not secrets.compare_digest(confirmation, _REMOTE_CONFIRMATION)
        ):
            raise UnsafeSeedTarget(_UNSAFE_TARGET_MESSAGE)
        return "approved Supabase development/demo"

    if (
        url.drivername != "sqlite+aiosqlite"
        or url.username is not None
        or url.password is not None
        or url.host is not None
        or url.port is not None
        or bool(url.query)
    ):
        raise UnsafeSeedTarget(_UNSAFE_TARGET_MESSAGE)

    if url.database == ":memory:":
        return "local SQLite (memory)"
    if not url.database:
        raise UnsafeSeedTarget(_UNSAFE_TARGET_MESSAGE)

    target = Path(url.database).resolve()
    if target.suffix.casefold() not in _SAFE_DATABASE_SUFFIXES:
        raise UnsafeSeedTarget(_UNSAFE_TARGET_MESSAGE)

    in_local_runtime = _is_within(target, SAFE_LOCAL_DATABASE_ROOT)
    in_disposable_test_dir = False
    if _is_within(target, SAFE_TEMP_ROOT):
        relative = target.relative_to(SAFE_TEMP_ROOT)
        in_disposable_test_dir = len(relative.parts) >= 2
    if not (in_local_runtime or in_disposable_test_dir):
        raise UnsafeSeedTarget(_UNSAFE_TARGET_MESSAGE)
    return f"local SQLite ({target.name})"


def _open_session_factory():
    # Importing core.db constructs the configured engine. Keep that import
    # behind validate_seed_target so unsafe URLs are refused first.
    from backend.app.core.db import session_factory

    return session_factory()()


def remote_seed_state_is_safe(
    non_seed_counts,
    *,
    user_total: int,
    known_users: int,
    policy_total: int,
    known_policies: int,
) -> bool:
    """Accept only an empty schema or a partial/complete known synthetic seed."""
    return (
        not any(non_seed_counts)
        and user_total == known_users
        and policy_total == known_policies
    )


def sid(kind: str, key: str) -> str:
    return str(uuid.uuid5(NAMESPACE, f"{kind}:{key}"))


#: Fictional helpline staff. No real person.
USERS = (
    {"username": "exec1", "role": "executive", "display_name": "Executive One"},
    {"username": "exec2", "role": "executive", "display_name": "Executive Two"},
    {"username": "sup1", "role": "supervisor", "display_name": "Supervisor One"},
)

#: Local retrieval corpus for the recommendation pathways.
#:
#: DEMO PLACEHOLDER CONTENT. These are neutral process notes written for this
#: project. They are NOT official policy, NOT quotations from any statute, rule
#: or scheme, and carry no real legal citation. An official policy corpus is
#: EXT-108 and still PROPOSED. Each note's `citation` is an internal
#: placeholder id so the console can show where a suggestion came from.
_PLACEHOLDER = "[DEMO PLACEHOLDER - not official policy] "
POLICY_CHUNKS = (
    {"key": "emergency", "source": "demo-placeholder", "citation": "DEMO-POLICY-01",
     "text": _PLACEHOLDER + "When a caller describes immediate danger, an officer considers "
             "emergency support first and records what was arranged.",
     "keywords": ["emergency", "immediate", "danger"]},
    {"key": "police", "source": "demo-placeholder", "citation": "DEMO-POLICY-02",
     "text": _PLACEHOLDER + "Where threats or intimidation are described, an officer considers "
             "whether police intervention is appropriate, with the caller's safety first.",
     "keywords": ["police", "threat", "intervention"]},
    {"key": "witness_protection", "source": "demo-placeholder", "citation": "DEMO-POLICY-03",
     "text": _PLACEHOLDER + "Where threats follow a complaint, an officer considers whether "
             "protective measures for the complainant or witnesses apply.",
     "keywords": ["witness", "protection", "complaint", "threat"]},
    {"key": "medical", "source": "demo-placeholder", "citation": "DEMO-POLICY-04",
     "text": _PLACEHOLDER + "Where someone is injured or needs treatment, an officer considers "
             "arranging medical assistance.",
     "keywords": ["medical", "injury", "treatment"]},
    {"key": "legal_aid", "source": "demo-placeholder", "citation": "DEMO-POLICY-05",
     "text": _PLACEHOLDER + "Where a complaint or FIR is involved, an officer considers whether "
             "free legal aid would help the caller.",
     "keywords": ["legal", "aid", "complaint", "fir"]},
    {"key": "counselling", "source": "demo-placeholder", "citation": "DEMO-POLICY-06",
     "text": _PLACEHOLDER + "Where a caller describes fear or ongoing distress, an officer "
             "considers offering counselling support.",
     "keywords": ["counselling", "support", "distress"]},
)


async def seed(reset: bool, password: str) -> int:
    settings = get_settings()
    database_url = (
        settings.database_url()
        if callable(getattr(settings, "database_url", None))
        else settings.DATABASE_URL
    )
    allow_remote = os.environ.get("SAHAY_REMOTE_DEMO_SEED") == "1"
    database_label = validate_seed_target(
        database_url,
        app_env=getattr(settings, "APP_ENV", "development"),
        allow_remote=allow_remote,
        project_ref=getattr(settings, "SUPABASE_PROJECT_REF", ""),
        confirmation=getattr(settings, "REMOTE_DEMO_SEED_CONFIRMATION", ""),
    )
    is_remote = database_label == "approved Supabase development/demo"
    if is_remote and reset:
        raise UnsafeSeedTarget(_UNSAFE_TARGET_MESSAGE)
    if not is_remote:
        settings.ensure_runtime_dirs()

    # Models import Base from core.db, so this must also remain after target
    # validation to avoid initializing a remote engine on an unsafe command.
    from backend.app.models import (
        Alert,
        Assessment,
        AuditLog,
        Case,
        Consent,
        DecisionAI,
        DecisionHuman,
        LatencyMetric,
        Override,
        PolicyChunk,
        Recommendation,
        Session,
        TimelineEvent,
        Turn,
        User,
    )

    async with _open_session_factory() as session:
        if is_remote:
            non_seed_tables = (
                Session,
                Consent,
                Turn,
                Case,
                Assessment,
                Alert,
                Recommendation,
                DecisionAI,
                DecisionHuman,
                Override,
                TimelineEvent,
                AuditLog,
                LatencyMetric,
            )
            non_seed_counts = [
                await session.scalar(select(func.count()).select_from(model))
                for model in non_seed_tables
            ]
            known_user_ids = [sid("user", spec["username"]) for spec in USERS]
            known_policy_ids = [sid("policy", spec["key"]) for spec in POLICY_CHUNKS]
            user_total = await session.scalar(select(func.count()).select_from(User))
            known_users = await session.scalar(
                select(func.count()).select_from(User).where(User.id.in_(known_user_ids))
            )
            policy_total = await session.scalar(select(func.count()).select_from(PolicyChunk))
            known_policies = await session.scalar(
                select(func.count()).select_from(PolicyChunk).where(PolicyChunk.id.in_(known_policy_ids))
            )
            if not remote_seed_state_is_safe(
                non_seed_counts,
                user_total=user_total,
                known_users=known_users,
                policy_total=policy_total,
                known_policies=known_policies,
            ):
                raise UnsafeSeedTarget(_UNSAFE_TARGET_MESSAGE)

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

    print(f"database:       {database_label}")
    print(f"users created:  {created or 'none (already present)'}")
    print(f"policy chunks:  {chunks or 'none (already present)'}")
    print("no victim, session, case or assessment data is seeded")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Seed an approved SAHAY-AI development database")
    parser.add_argument("--reset", action="store_true",
                        help="delete seeded users and policy chunks first")
    args = parser.parse_args(argv)

    password = os.environ.get("SEED_PASSWORD")
    generated = password is None
    if generated:
        password = secrets.token_urlsafe(12)

    try:
        code = asyncio.run(seed(args.reset, password))
    except UnsafeSeedTarget:
        print(_UNSAFE_TARGET_MESSAGE, file=sys.stderr)
        return 2

    if generated:
        print()
        print("Generated a local demo password for every seeded account:")
        print(f"    {password}")
        print("It is not stored anywhere but the password hash. Set SEED_PASSWORD "
              "to choose your own. Never use this on anything but a local demo.")
    return code


if __name__ == "__main__":
    sys.exit(main())
