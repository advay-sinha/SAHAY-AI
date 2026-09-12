"""Contract-drift guard across the three hand-maintained copies of one contract.

`docs/contracts/CONTRACTS.md` is the frozen source. These places restate it:

    backend/app/ws/events.py        the role allowlists the socket enforces
    backend/app/core/enums.py       the frozen enumerations (PC-10)
    backend/app/models/tables.py    the table list (section 6)
    ml/svi/dimensions.py            the SVI weights the engine applies
    ml/assessment.py                the text channels (PC-08)
    frontend/src/types/contracts.ts the console's typed mirror
    mobile/src/types/events.ts      the victim app's event allowlist

Hand-maintained copies drift, and the failure mode here is an assessment event
reaching a victim client. This test reads all four files as text and asserts
they agree.

Standard library only, so it runs with no installed dependency:
    python -m unittest discover -s backend/tests -t .
"""

import pathlib
import re
import unittest

from backend.app.ws.events import EXECUTIVE_ONLY, VICTIM_ALLOWED

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACTS_MD = REPO_ROOT / "docs" / "contracts" / "CONTRACTS.md"
DIMENSIONS_PY = REPO_ROOT / "ml" / "svi" / "dimensions.py"
CONTRACTS_TS = REPO_ROOT / "frontend" / "src" / "types" / "contracts.ts"
MOBILE_EVENTS_TS = REPO_ROOT / "mobile" / "src" / "types" / "events.ts"
TABLES_PY = REPO_ROOT / "backend" / "app" / "models" / "tables.py"
SCHEMAS_PY = REPO_ROOT / "backend" / "app" / "schemas" / "contracts.py"


def contract_section(doc: str, number: int) -> str:
    match = re.search(rf"^## {number}\..*?(?=^## \d+\.|\Z)", doc, re.MULTILINE | re.DOTALL)
    if match is None:
        raise AssertionError(f"CONTRACTS.md section {number} not found")
    return match.group(0)


def documented_enums() -> dict:
    """Parse the <!-- enums:begin --> block in CONTRACTS.md section 9."""
    block = re.search(r"<!-- enums:begin -->(.*?)<!-- enums:end -->", read(CONTRACTS_MD), re.DOTALL)
    if block is None:
        raise AssertionError("CONTRACTS.md has no enums block")
    out = {}
    for line in block.group(1).splitlines():
        m = re.match(r"^([a-z_]+)\s{2,}(.+)$", line.strip())
        if m:
            out[m.group(1)] = [v.strip() for v in m.group(2).split("|")]
    return out


def ts_ordered_array(source: str, name: str) -> list:
    match = re.search(rf"export const {name}\s*=\s*\[(.*?)\]", source, re.DOTALL)
    if match is None:
        raise AssertionError(f"{name} not found")
    return re.findall(r'"([^"]+)"', match.group(1))


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def ts_string_array(source: str, name: str) -> list:
    """Extract the string literals from `export const NAME = [ ... ] as const;`."""
    match = re.search(rf"{name}\s*=\s*\[(.*?)\]", source, re.DOTALL)
    if match is None:
        raise AssertionError(f"{name} not found in contracts.ts")
    return sorted(re.findall(r'"([^"]+)"', match.group(1)))


def ts_number_map(source: str, name: str) -> dict:
    """Extract `D1: 0.22,` pairs from a `export const NAME: ... = { ... };` block."""
    match = re.search(rf"{name}[^=]*=\s*\{{(.*?)\}}", source, re.DOTALL)
    if match is None:
        raise AssertionError(f"{name} not found in contracts.ts")
    return {k: float(v) for k, v in re.findall(r"(D[1-9])\s*:\s*([0-9.]+)", match.group(1))}


class TestEventAllowlistMirror(unittest.TestCase):
    """backend/app/ws/events.py vs frontend/src/types/contracts.ts."""

    def setUp(self):
        self.ts = read(CONTRACTS_TS)

    def test_victim_allowlist_matches_the_console_mirror(self):
        self.assertEqual(
            ts_string_array(self.ts, "VICTIM_ALLOWED_EVENTS"),
            sorted(VICTIM_ALLOWED),
        )

    def test_executive_only_matches_the_console_mirror(self):
        self.assertEqual(
            ts_string_array(self.ts, "EXECUTIVE_ONLY_EVENTS"),
            sorted(EXECUTIVE_ONLY),
        )

    def test_the_console_mirror_never_overlaps(self):
        victim = set(ts_string_array(self.ts, "VICTIM_ALLOWED_EVENTS"))
        executive = set(ts_string_array(self.ts, "EXECUTIVE_ONLY_EVENTS"))
        self.assertEqual(victim & executive, set())

    def test_every_event_name_appears_in_the_frozen_contract(self):
        doc = read(CONTRACTS_MD)
        for event in sorted(VICTIM_ALLOWED | EXECUTIVE_ONLY):
            self.assertIn(event, doc, msg=f"{event} is not in CONTRACTS.md")


class TestMobileAllowlistMirror(unittest.TestCase):
    """Mobile contract gap: backend, mobile mirror and CONTRACTS.md section 2 agree."""

    def test_mobile_allowlist_equals_backend_and_the_contract(self):
        mobile = ts_string_array(read(MOBILE_EVENTS_TS), "ALLOWED_EVENT_TYPES")
        documented = sorted(re.findall(r"^([a-z]+\.[a-z_]+)\s", contract_section(read(CONTRACTS_MD), 2),
                                       re.MULTILINE))
        self.assertEqual(mobile, sorted(VICTIM_ALLOWED))
        self.assertEqual(documented, sorted(VICTIM_ALLOWED))

    def test_mobile_never_lists_an_executive_event(self):
        mobile = set(ts_string_array(read(MOBILE_EVENTS_TS), "ALLOWED_EVENT_TYPES"))
        self.assertEqual(mobile & set(EXECUTIVE_ONLY), set())

    def test_mobile_union_covers_exactly_the_allowlist(self):
        union = re.search(r"export type VictimEvent\s*=(.*?);", read(MOBILE_EVENTS_TS), re.DOTALL).group(1)
        self.assertEqual(sorted(re.findall(r'type:\s*"([^"]+)"', union)), sorted(VICTIM_ALLOWED))

    def test_officer_message_origin_is_human_in_every_copy(self):
        for path in (MOBILE_EVENTS_TS, CONTRACTS_TS, SCHEMAS_PY, CONTRACTS_MD):
            self.assertIn('"human_officer"', read(path), msg=str(path))


class TestEnumMirror(unittest.TestCase):
    """PC-10: CONTRACTS.md section 9 vs core/enums.py vs contracts.ts."""

    PAIRS = {
        "session_channel": "SESSION_CHANNELS",
        "text_channel": "TEXT_CHANNELS",
        "session_state": "SESSION_STATES",
        "consent_status": "CONSENT_STATUSES",
        "case_status": "CASE_STATUSES",
        "band": "BANDS",
        "alert_type": "ALERT_TYPES",
        "alert_severity": "ALERT_SEVERITIES",
        "recommendation_pathway": "RECOMMENDATION_PATHWAYS",
        "decision": "DECISIONS",
        "role": "ROLES",
        "timeline_stage": "TIMELINE_STAGES",
        "turn_speaker": "TURN_SPEAKERS",
    }

    def test_every_enum_agrees_in_all_three_places(self):
        from backend.app.core import enums

        doc = documented_enums()
        ts = read(CONTRACTS_TS)
        self.assertEqual(set(doc), set(self.PAIRS))
        for key, name in self.PAIRS.items():
            self.assertEqual(list(getattr(enums, name)), doc[key], msg=f"backend {key}")
            self.assertEqual(ts_ordered_array(ts, name), doc[key], msg=f"frontend {key}")

    def test_ml_text_channels_match(self):
        from ml.assessment import AUDIO_CHANNELS, TEXT_CHANNELS

        doc = documented_enums()
        self.assertEqual(list(TEXT_CHANNELS), doc["text_channel"])
        self.assertEqual(sorted(TEXT_CHANNELS + AUDIO_CHANNELS), sorted(doc["session_channel"]))

    def test_schema_literals_are_built_from_the_enums(self):
        schemas = read(SCHEMAS_PY)
        for alias, name in (("Channel", "SESSION_CHANNELS"), ("ConsentStatus", "CONSENT_STATUSES"),
                            ("Band", "BANDS"), ("Decision", "DECISIONS"), ("AlertType", "ALERT_TYPES"),
                            ("AlertSeverity", "ALERT_SEVERITIES"), ("TimelineStage", "TIMELINE_STAGES")):
            self.assertRegex(schemas, rf"(?m)^{alias} = Literal\[{name}\]$", msg=alias)

    def test_engine_bands_match(self):
        from ml.svi.dimensions import BANDS as ENGINE_BANDS

        self.assertEqual(sorted(name for _lo, name in ENGINE_BANDS), sorted(documented_enums()["band"]))

    def test_there_is_one_timeline_stage_list(self):
        """The duplicate backend timeline lists are gone: everything imports core/enums."""
        app = REPO_ROOT / "backend" / "app"
        offenders = [str(p.relative_to(app)) for p in app.rglob("*.py")
                     if p.name != "enums.py"
                     and re.search(r'"request_received"\s*,\s*"under_review"', read(p))]
        self.assertEqual(offenders, [])


class TestTableList(unittest.TestCase):
    """CONTRACTS.md section 6 vs the models (PC-11: 16 tables)."""

    def test_models_declare_exactly_the_contract_tables(self):
        section = contract_section(read(CONTRACTS_MD), 6)
        listed = re.search(r"`(users[^`]*)`", section).group(1)
        documented = sorted(t.strip() for t in listed.split("·"))
        declared = sorted(re.findall(r'__tablename__\s*=\s*"([^"]+)"', read(TABLES_PY)))
        self.assertEqual(declared, documented)
        self.assertEqual(len(declared), 16)
        self.assertIn("16 tables", section)


class TestSviWeightMirror(unittest.TestCase):
    """CONTRACTS.md section 7 vs ml/svi/dimensions.py vs contracts.ts."""

    def setUp(self):
        self.doc = read(CONTRACTS_MD)
        self.ts = read(CONTRACTS_TS)
        from ml.svi.dimensions import WEIGHTS

        self.engine_weights = dict(WEIGHTS)

    def _documented_weights(self) -> dict:
        # Rows look like: | D1 | Immediate safety threat | 0.22 |
        found = re.findall(r"\|\s*(D[1-9])\s*\|[^|]*\|\s*([0-9.]+)\s*\|", self.doc)
        self.assertEqual(len(found), 9, msg="CONTRACTS.md section 7 must list nine dimensions")
        return {k: float(v) for k, v in found}

    def test_engine_matches_the_frozen_contract(self):
        self.assertEqual(self.engine_weights, self._documented_weights())

    def test_console_mirror_matches_the_frozen_contract(self):
        self.assertEqual(
            ts_number_map(self.ts, "DIMENSION_WEIGHTS"),
            self._documented_weights(),
        )

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(self._documented_weights().values()), 1.0, places=6)

    def test_dimension_labels_agree(self):
        from ml.svi.dimensions import DIMENSION_LABELS

        ts_labels = dict(
            re.findall(r'(D[1-9]):\s*"([^"]+)"', re.search(
                r"DIMENSION_LABELS[^=]*=\s*\{(.*?)\}", self.ts, re.DOTALL
            ).group(1))
        )
        self.assertEqual(ts_labels, dict(DIMENSION_LABELS))


class TestBandMirror(unittest.TestCase):
    def test_band_thresholds_match_the_frozen_contract(self):
        from ml.svi.dimensions import BANDS

        doc = read(CONTRACTS_MD)
        # "**Bands:** 0-29 Low . 30-54 Moderate . 55-74 High . 75-100 Critical."
        found = re.findall(r"(\d+)\s*[-–]\s*(\d+)\s+(Low|Moderate|High|Critical)", doc)
        self.assertEqual(len(found), 4, msg="CONTRACTS.md must state four bands")
        # The engine stores lower bounds (a continuous score has no gaps).
        documented = sorted(((float(lo), name) for lo, _hi, name in found), reverse=True)
        self.assertEqual(list(BANDS), documented)


class TestOverrideThresholdsAreDocumented(unittest.TestCase):
    def test_confidence_floor_matches_the_contract(self):
        from ml.svi.overrides import CONFIDENCE_FLOOR

        doc = read(CONTRACTS_MD)
        self.assertIn(str(CONFIDENCE_FLOOR), doc,
                      msg="the abstention floor in overrides.py is not the one CONTRACTS.md states")

    def test_env_example_declares_the_same_floor(self):
        from ml.svi.overrides import CONFIDENCE_FLOOR

        env = read(REPO_ROOT / ".env.example")
        match = re.search(r"SVI_CONFIDENCE_FLOOR=([0-9.]+)", env)
        self.assertIsNotNone(match, msg="SVI_CONFIDENCE_FLOOR missing from .env.example")
        self.assertAlmostEqual(float(match.group(1)), CONFIDENCE_FLOOR, places=6)


if __name__ == "__main__":
    unittest.main()
