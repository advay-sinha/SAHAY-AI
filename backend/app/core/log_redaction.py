"""Keep tokens and submitted narrative out of server logs.

The approved WebSocket contract carries credentials only in the exact first
client frame and rejects every URL query component. This filter remains as
defence in depth so malformed or hostile requests cannot put a credential into
uvicorn, proxy, or application logs.

It also pins SQL-logging libraries to WARNING, because they log bound
parameters -- and a parameter can be a victim's message.

This filter rewrites log records before any handler sees them:
  * `token=` / `access_token=` / `jwt=` query values become `[REDACTED]`
  * anything shaped like a JWT (three base64url segments starting `eyJ`)
    becomes `[REDACTED-JWT]`, wherever it appears

It is a fallback control, not permission for a client to put credentials in a
URL or log frame contents.
"""

import logging
import re

_QUERY_TOKEN = re.compile(r"(?i)([?&](?:token|access_token|jwt)=)[^&\s\"']+")
_JWT_SHAPE = re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}")

REDACTED = "[REDACTED]"
REDACTED_JWT = "[REDACTED-JWT]"

#: Loggers that can carry a request path. uvicorn logs WebSocket handshakes on
#: uvicorn.error and HTTP requests on uvicorn.access.
LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi")


def redact(text: str) -> str:
    text = _QUERY_TOKEN.sub(lambda m: m.group(1) + REDACTED, text)
    return _JWT_SHAPE.sub(REDACTED_JWT, text)


def _clean(value):
    return redact(value) if isinstance(value, str) else value


class TokenRedactionFilter(logging.Filter):
    """Redacts the message template and every string argument IN PLACE.

    The shape of `record.args` must be preserved. uvicorn's AccessFormatter
    unpacks it as exactly five values (client, method, path, version, status);
    an earlier version of this filter replaced args with `()` after formatting
    the message itself, which made the formatter raise and silently dropped
    every access-log line that contained a token.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_clean(a) for a in record.args)
        elif isinstance(record.args, dict):
            record.args = {k: _clean(v) for k, v in record.args.items()}
        return True


_FILTER = TokenRedactionFilter()


#: Libraries that log SQL statements WITH their bound parameters at DEBUG or
#: INFO. A parameter can be a victim's message (INSERT INTO turns ...), so these
#: are pinned to WARNING: turning the root logger up to DEBUG for troubleshooting
#: must never write a narrative to disk.
DATA_LOGGERS = ("aiosqlite", "sqlalchemy.engine", "sqlalchemy.pool", "sqlalchemy.orm",
                "sqlalchemy.dialects")


def install() -> None:
    """Attach the redaction filter and quieten data-bearing loggers. Idempotent."""
    for name in LOGGERS:
        logger = logging.getLogger(name)
        if _FILTER not in logger.filters:
            logger.addFilter(_FILTER)
    for name in DATA_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
