"""Authentication and RBAC for the executive console.

Covers: seeded-credential login, safe and uniform failures (no username
enumeration), pwdlib/Argon2 hashing, JWT claims, rejection of missing /
malformed / expired / forged tokens, Executive vs Supervisor vs Victim
boundaries, query-string tokens being ignored on REST, log redaction of the
contract-mandated WebSocket token, and no password or hash leaking.

Every test runs against a disposable SQLite file, wired in through FastAPI's
dependency override. The development database is never touched.

Tokens stay in memory and travel in the `Authorization: Bearer` header only.

Needs the EXT-001 packages; under the bare-interpreter Tier 1 run it skips.
"""

import importlib.util
import io
import logging
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

_DEPS = ("fastapi", "pydantic_settings", "sqlalchemy", "aiosqlite", "jwt", "pwdlib", "httpx")
HAVE_DEPS = all(importlib.util.find_spec(m) is not None for m in _DEPS)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

#: Local test credentials. Never used outside this disposable database.
PASSWORD = "test-only-not-a-real-password"


def _build_db(path: str):
    """Create the schema and three users with a synchronous engine."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from backend.app.core.db import Base
    from backend.app.core.security import hash_password
    import backend.app.models  # noqa: F401  registers every table
    from backend.app.models import User

    sync = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(sync)
    with Session(sync) as s:
        s.add_all([
            User(id="u-exec", username="exec1", password_hash=hash_password(PASSWORD),
                 role="executive", display_name="Executive One"),
            User(id="u-sup", username="sup1", password_hash=hash_password(PASSWORD),
                 role="supervisor", display_name="Supervisor One"),
            # A row that must never reach the console, even with the right password.
            User(id="u-vic", username="victimrow", password_hash=hash_password(PASSWORD),
                 role="victim", display_name="Not a console user"),
        ])
        s.commit()
    sync.dispose()


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class AuthTestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import jwt
        from fastapi.testclient import TestClient
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from backend.app.core.config import get_settings
        from backend.app.core.db import get_session
        from backend.app.main import app

        cls.jwt = jwt
        cls.settings = get_settings()
        cls.tmpdir = tempfile.TemporaryDirectory()
        db_path = os.path.join(cls.tmpdir.name, "auth-test.db").replace("\\", "/")
        _build_db(db_path)

        # NullPool: no connection outlives the event loop that opened it.
        cls.engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", poolclass=NullPool)
        maker = async_sessionmaker(cls.engine, class_=AsyncSession, expire_on_commit=False)

        async def _override():
            async with maker() as session:
                yield session

        cls.app = app
        app.dependency_overrides[get_session] = _override
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        from backend.app.core.db import get_session

        cls.app.dependency_overrides.pop(get_session, None)
        cls.client.close()
        cls.tmpdir.cleanup()

    # helpers -------------------------------------------------------------
    def login(self, username, password=PASSWORD):
        return self.client.post("/auth/login", json={"username": username, "password": password})

    def token_for(self, username):
        r = self.login(username)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()["token"]

    def bearer(self, token):
        return {"Authorization": f"Bearer {token}"}

    def forge(self, claims, key=None, algorithm=None):
        return self.jwt.encode(
            claims,
            key if key is not None else self.settings.SECRET_KEY,
            algorithm=algorithm or self.settings.JWT_ALGORITHM,
        )


class TestLogin(AuthTestBase):
    def test_executive_login_returns_token_and_role(self):
        r = self.login("exec1")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(set(body), {"token", "role", "display_name"})
        self.assertEqual(body["role"], "executive")
        self.assertEqual(body["display_name"], "Executive One")

    def test_supervisor_login_returns_supervisor_role(self):
        self.assertEqual(self.login("sup1").json()["role"], "supervisor")

    def test_token_carries_minimum_claims(self):
        from backend.app.core.security import decode_token

        claims = decode_token(self.token_for("exec1"))
        for claim in ("sub", "role", "iat", "exp"):
            self.assertIn(claim, claims)
        self.assertEqual(claims["sub"], "u-exec")
        self.assertEqual(claims["role"], "executive")
        self.assertEqual(claims["exp"] - claims["iat"], self.settings.JWT_EXPIRY_MINUTES * 60)
        # No credential material in the token.
        self.assertFalse({"password", "password_hash", "username"} & set(claims))

    def test_wrong_password_and_unknown_user_are_indistinguishable(self):
        wrong = self.login("exec1", "nope")
        unknown = self.login("no-such-user", "nope")
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(unknown.status_code, 401)
        self.assertEqual(wrong.json(), unknown.json())
        self.assertEqual(wrong.json(), {"detail": "Invalid username or password"})
        self.assertEqual(wrong.headers.get("www-authenticate"), "Bearer")

    def test_both_failure_paths_do_the_same_argon2_work(self):
        from backend.app.core import security

        calls = []
        real = security.password_hash.verify

        def counting(*args, **kwargs):
            calls.append(1)
            return real(*args, **kwargs)

        security.password_hash.verify = counting
        try:
            self.login("exec1", "nope")
            wrong_calls = len(calls)
            calls.clear()
            self.login("no-such-user", "nope")
            unknown_calls = len(calls)
        finally:
            security.password_hash.verify = real
        self.assertEqual(wrong_calls, 1)
        self.assertEqual(unknown_calls, 1)

    def test_a_non_console_role_cannot_log_in_even_with_the_right_password(self):
        r = self.login("victimrow")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json(), {"detail": "Invalid username or password"})

    def test_empty_or_oversized_input_is_rejected_without_revealing_anything(self):
        self.assertEqual(self.login("exec1", "").status_code, 422)
        self.assertEqual(self.login("exec1", "x" * 1000).status_code, 422)

    def test_response_never_contains_password_or_hash(self):
        text = self.login("exec1").text
        self.assertNotIn("$argon2", text)
        self.assertNotIn(PASSWORD, text)
        self.assertNotIn("password", text.lower())

    def test_openapi_exposes_no_hash_field(self):
        spec = self.client.get("/openapi.json").json()
        self.assertNotIn("password_hash", str(spec))
        props = spec["components"]["schemas"]["LoginResponse"]["properties"]
        self.assertEqual(sorted(props), ["display_name", "role", "token"])


class TestPasswordHashing(AuthTestBase):
    def test_hashes_are_argon2id_via_pwdlib(self):
        from pwdlib.hashers.argon2 import Argon2Hasher

        from backend.app.core.security import hash_password, password_hash

        self.assertTrue(any(isinstance(h, Argon2Hasher) for h in password_hash.hashers))
        hashed = hash_password("x")
        self.assertTrue(hashed.startswith("$argon2id$"), hashed[:12])
        self.assertNotEqual(hashed, hash_password("x"), "Argon2 must salt per call")


class TestTokenRejection(AuthTestBase):
    UNAUTH = {"detail": "Not authenticated"}

    def assert_401(self, headers=None, path="/queue", params=None):
        r = self.client.get(path, headers=headers or {}, params=params)
        self.assertEqual(r.status_code, 401, r.text)
        self.assertEqual(r.json(), self.UNAUTH)
        self.assertEqual(r.headers.get("www-authenticate"), "Bearer")

    def _now(self):
        return datetime.now(timezone.utc)

    def test_missing_header(self):
        self.assert_401()

    def test_wrong_scheme_or_empty_credentials(self):
        self.assert_401({"Authorization": "Bearer"})
        self.assert_401({"Authorization": "Bearer    "})
        self.assert_401({"Authorization": f"Basic {self.token_for('exec1')}"})

    def test_malformed_token(self):
        self.assert_401(self.bearer("not-a-jwt"))
        self.assert_401(self.bearer("a.b.c"))

    def test_expired_token(self):
        past = self._now() - timedelta(hours=2)
        token = self.forge({"sub": "u-exec", "role": "executive",
                            "iat": past, "exp": past + timedelta(minutes=1)})
        self.assert_401(self.bearer(token))

    def test_wrong_signing_key(self):
        now = self._now()
        token = self.forge({"sub": "u-exec", "role": "supervisor", "iat": now,
                            "exp": now + timedelta(hours=1)}, key="attacker-key-" + "x" * 40)
        self.assert_401(self.bearer(token))

    def test_alg_none_is_rejected(self):
        now = self._now()
        token = self.jwt.encode({"sub": "u-exec", "role": "supervisor", "iat": now,
                                 "exp": now + timedelta(hours=1)}, key=None, algorithm="none")
        self.assert_401(self.bearer(token))

    def test_missing_required_claims(self):
        now = self._now()
        for missing in ("role", "exp", "sub", "iat"):
            claims = {"sub": "u-exec", "role": "executive", "iat": now,
                      "exp": now + timedelta(hours=1)}
            del claims[missing]
            with self.subTest(missing=missing):
                self.assert_401(self.bearer(self.forge(claims)))

    def test_unknown_role_claim(self):
        now = self._now()
        token = self.forge({"sub": "u-x", "role": "admin", "iat": now,
                            "exp": now + timedelta(hours=1)})
        self.assert_401(self.bearer(token))

    def test_a_token_in_the_query_string_is_ignored_on_rest(self):
        # A perfectly valid token, offered only through the URL, grants nothing.
        self.assert_401(params={"token": self.token_for("exec1")})
        self.assert_401(params={"access_token": self.token_for("exec1")})


class TestRbac(AuthTestBase):
    def victim_token(self):
        from backend.app.core.security import create_token

        return create_token("victim-1", "victim", session_id="s1")

    def test_executive_and_supervisor_can_use_the_console(self):
        for user in ("exec1", "sup1"):
            with self.subTest(user=user):
                r = self.client.get("/queue", headers=self.bearer(self.token_for(user)))
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json(), [])

    def test_a_victim_token_is_forbidden_on_console_routes(self):
        headers = self.bearer(self.victim_token())
        for method, path in (("get", "/queue"), ("get", "/cases/c1"),
                             ("get", "/cases/c1/audit"), ("post", "/cases/c1/claim"),
                             ("post", "/cases/c1/takeover")):
            with self.subTest(path=path):
                r = getattr(self.client, method)(path, headers=headers)
                self.assertEqual(r.status_code, 403)
                self.assertEqual(r.json(), {"detail": "Not permitted for this role"})

    def test_a_victim_token_may_reach_the_victim_safe_timeline(self):
        # Past the role check (not 401/403); the case simply does not exist here.
        # Own-case scoping is covered in test_vertical_slice.py.
        r = self.client.get("/cases/c1/timeline", headers=self.bearer(self.victim_token()))
        self.assertEqual(r.status_code, 404)

    def test_protected_routes_reject_anonymous_callers_before_validating_bodies(self):
        r = self.client.post("/cases/c1/override", json={"band": "Critical", "reason": ""})
        self.assertIn(r.status_code, (401, 422))
        r = self.client.post("/cases/c1/override", json={"band": "Critical", "reason": "x"})
        self.assertEqual(r.status_code, 401)

    def test_supervisor_only_boundary(self):
        """Supervisor endpoints are BE-021 (P3). The dependency they will use is
        tested here on a throwaway app, so the boundary exists before they do."""
        from fastapi import Depends, FastAPI
        from fastapi.testclient import TestClient

        from backend.app.core.auth import Principal, require_supervisor

        probe = FastAPI()

        @probe.get("/supervisor-only")
        def _only(principal: Principal = Depends(require_supervisor)):
            return {"role": principal.role}

        with TestClient(probe) as c:
            self.assertEqual(
                c.get("/supervisor-only", headers=self.bearer(self.token_for("sup1"))).status_code, 200)
            self.assertEqual(
                c.get("/supervisor-only", headers=self.bearer(self.token_for("exec1"))).status_code, 403)
            self.assertEqual(
                c.get("/supervisor-only", headers=self.bearer(self.victim_token())).status_code, 403)
            self.assertEqual(c.get("/supervisor-only").status_code, 401)


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestLogRedaction(unittest.TestCase):
    def test_websocket_handshake_token_is_redacted(self):
        from backend.app.core.log_redaction import redact

        line = ('127.0.0.1:5000 - "WebSocket /ws/session/s1?token='
                'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.abcdefghijk" [accepted]')
        cleaned = redact(line)
        self.assertNotIn("eyJ", cleaned)
        self.assertIn("token=[REDACTED]", cleaned)

    def test_bare_jwt_anywhere_is_redacted(self):
        from backend.app.core.log_redaction import redact

        cleaned = redact("auth failed for eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.abcdefghijk here")
        self.assertEqual(cleaned, "auth failed for [REDACTED-JWT] here")

    def test_the_installed_filter_rewrites_uvicorn_records(self):
        from backend.app.core import log_redaction

        log_redaction.install()
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = logging.getLogger("uvicorn.error")
        logger.addHandler(handler)
        old_level = logger.level
        logger.setLevel(logging.INFO)
        try:
            logger.info('%s - "WebSocket %s" [accepted]', "127.0.0.1:1",
                        "/ws/session/s1?token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.abcdefghijk")
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)
        self.assertNotIn("eyJ", stream.getvalue())
        self.assertIn("[REDACTED]", stream.getvalue())

    def test_uvicorn_access_formatter_still_formats_redacted_records(self):
        """Regression: redaction must keep record.args a 5-tuple, or uvicorn's
        AccessFormatter raises and the whole access-log line is lost."""
        from uvicorn.logging import AccessFormatter

        from backend.app.core.log_redaction import TokenRedactionFilter

        token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.abcdefghijk"
        record = logging.LogRecord(
            name="uvicorn.access", level=logging.INFO, pathname=__file__, lineno=1,
            msg='%s - "%s %s HTTP/%s" %d',
            args=("127.0.0.1:1", "GET", f"/queue?token={token}", "1.1", 401),
            exc_info=None,
        )
        self.assertTrue(TokenRedactionFilter().filter(record))
        self.assertEqual(len(record.args), 5)
        line = AccessFormatter('%(client_addr)s - "%(request_line)s" %(status_code)s',
                               use_colors=False).format(record)
        self.assertIn("/queue?token=[REDACTED]", line)
        self.assertNotIn("eyJ", line)
        self.assertIn("401", line)


@unittest.skipUnless(HAVE_DEPS, "EXT-001 backend packages not installed (Tier 1 run)")
class TestSeedDoesNotLeak(unittest.TestCase):
    def test_seed_prints_neither_hash_nor_supplied_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = os.path.join(tmp, "seed-leak.db").replace("\\", "/")
            code = (
                "import asyncio\n"
                "import backend.app.models\n"
                "from backend.app.core.db import Base, engine\n"
                "async def mk():\n"
                "    async with engine.begin() as c:\n"
                "        await c.run_sync(Base.metadata.create_all)\n"
                "    await engine.dispose()\n"
                "asyncio.run(mk())\n"
                "from backend.seed.seed import main\n"
                "raise SystemExit(main(['--reset']))\n"
            )
            env = dict(os.environ)
            env["DATABASE_URL"] = f"sqlite+aiosqlite:///{db}"
            env["SEED_PASSWORD"] = "supplied-secret-value-xyz"
            result = subprocess.run([sys.executable, "-c", code], cwd=str(REPO_ROOT), env=env,
                                    capture_output=True, text=True, timeout=180)
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])
            out = result.stdout + result.stderr
            self.assertNotIn("$argon2", out)
            self.assertNotIn("supplied-secret-value-xyz", out)
            self.assertIn("local", out.lower())


if __name__ == "__main__":
    unittest.main()
