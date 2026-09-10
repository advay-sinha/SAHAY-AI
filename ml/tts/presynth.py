"""Pre-synthesised fixed-script audio registry.

S0, S9 and SX audio is rendered once, reviewed, and stored under DATA_ROOT.
Only the asset name lives in Git. Audio is never committed.
"""

from typing import Dict, Optional

#: "<state>:<lang>" -> asset filename under DATA_ROOT/audio/fixed/
ASSETS: Dict[str, Optional[str]] = {
    "S0:hi": None,
    "S0:en": None,
    "S9:hi": None,
    "S9:en": None,
    "SX:hi": None,
    "SX:en": None,
    "SH:hi": None,
    "SH:en": None,
}


def asset_for(state: str, lang: str) -> Optional[str]:
    return ASSETS.get(f"{state}:{lang}")


def missing() -> Dict[str, Optional[str]]:
    return {key: value for key, value in ASSETS.items() if value is None}
