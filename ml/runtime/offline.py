"""Offline enforcement: environment switches plus an active socket block. Standard library only.

``apply_offline_env()`` sets the Hugging Face offline switches before any Hugging Face module is
imported; every load path calls it. ``network_blocked()`` goes further for verification: it
replaces the socket entry points so any connection attempt raises and is counted, which proves
a reload is offline rather than merely disconnected.
"""

import contextlib
import os
import socket
from typing import Dict, Iterator

OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
    "HF_HUB_DISABLE_PROGRESS_BARS": "1",
    "DO_NOT_TRACK": "1",
}


class NetworkBlocked(OSError):
    """Raised for any connection attempt inside ``network_blocked()``."""


def apply_offline_env() -> None:
    for key, value in OFFLINE_ENV.items():
        os.environ[key] = value


@contextlib.contextmanager
def network_blocked() -> Iterator[Dict[str, int]]:
    """Block and count every outbound connection and DNS lookup for the duration."""
    record = {"attempts": 0}
    saved = (socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo)

    def refuse(*_args, **_kwargs):
        record["attempts"] += 1
        raise NetworkBlocked("network access is blocked during offline verification")

    socket.socket.connect = refuse
    socket.socket.connect_ex = refuse
    socket.create_connection = refuse
    socket.getaddrinfo = refuse
    previous = {k: os.environ.get(k) for k in OFFLINE_ENV}
    apply_offline_env()
    try:
        yield record
    finally:
        socket.socket.connect, socket.socket.connect_ex, socket.create_connection, socket.getaddrinfo = saved
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
