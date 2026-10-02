"""Domain errors and safe error responses.

Services raise these; main.py turns them into JSON with a short, fixed
message. Nothing here carries a stack trace, a secret, or victim text.
"""


class DomainError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BadRequest(DomainError):
    status_code = 400


class Forbidden(DomainError):
    status_code = 403


class NotFound(DomainError):
    status_code = 404


class Conflict(DomainError):
    """An invalid state transition or a clash with an existing record."""

    status_code = 409


class PayloadTooLarge(DomainError):
    status_code = 413


class UnsupportedMediaType(DomainError):
    status_code = 415


class TooManyRequests(DomainError):
    """PC-13: a client created too many sessions in a rolling hour."""

    status_code = 429


class ServiceUnavailable(DomainError):
    """A local dependency (for example speech recognition) is not reachable."""

    status_code = 503
