"""External-corpus intake tests. Standard library only; offline.

Every dataset here is a SMALL FICTIONAL TEMPORARY FILE created inside a temporary
directory and deleted when the test ends. None of it comes from, or depends on,
SAHAY_DATASETS_ROOT; the variable is removed from the environment for every
test in this module. The fictional rows are flat invented sentences about forms,
buses and weather, chosen so they carry no real narrative.
"""

import copy
import csv
import io
import json
import os
import re
import tempfile
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from ml.data import archive_safety as az
from ml.data import audit_external as audit
from ml.data import external_corpus as xc
from ml.data import external_analysis as xg
from ml.data import external_report as xr
from ml.data import governance as gov
from ml.data import inventory as inv
from ml.data import label_firewall as fw
from ml.eval import contamination as ct
from ml.tests.source_scan import iter_source_files

ML = Path(__file__).resolve().parents[1]
REPO = ML.parent
DATASET_ID = "fictional_test_corpus"
TS = "2026-09-12T10:00:00+05:30"

ROWS = [
    ("I filled in the bus pass form and posted it at the counter.", "happy", "train"),
    ("The weather was cloudy and the queue at the office was long.", "sad", "train"),
    ("Please check https://example.invalid/x and write to a.b@example.invalid today.", "happy", "test"),
    ("Ask u/fictional_user and @fictional_handle about the timetable change.", "sad", "test"),
    ("I filled in the bus pass form and posted it at the counter.", "happy", "train"),        # exact dup
    ("the counter and posted it I filled in the bus pass form at.", "sad", "train"),          # near dup
    ("A sentence with an unknown label value in it for the test.", "furious", "train"),       # unsupported
    ("A sentence with a split value nobody recognises at all here.", "happy", "holdout"),     # bad split
]

SPEC = {
    "format": "csv", "text_column": "text", "label_column": "mood", "split_column": "split",
    "language": "en", "language_column": None, "multi_label": False,
    "label_families": {"happy": "sentiment_positive", "sad": "sentiment_negative"},
    "ontology_verified": True, "ontology_evidence": "fictional test spec",
}


def write_csv(path: Path, rows, header=("text", "mood", "split")) -> None:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buf.getvalue(), encoding="utf-8", newline="")


def fictional_registry(rel: str, path: Path, review_status: str = "approved_for_research",
                       dataset_id: str = DATASET_ID) -> dict:
    """A temporary registry holding one fictional record, shaped exactly like the real ones."""
    real = gov.load_registry()
    record = copy.deepcopy(gov.get(real, "emoinhindi"))
    record.update({
        "id": dataset_id, "name": "Fictional test corpus (TEST ONLY)", "version": "test-1",
        "modality": "text", "primary_language": "en", "additional_languages": [],
        "licence_name": "Fictional test licence", "licence_url": "https://example.invalid/licence",
        "redistribution": "not_permitted", "commercial_use": "not_permitted",
        "local_relative_path": rel, "archive_filename": Path(rel).name,
        "byte_size": path.stat().st_size, "sha256": az.sha256_file(path),
        "archive_safety_status": "not_applicable", "extraction_status": "not_applicable",
        "review_status": review_status,
        "approved_uses": ["research"] if review_status.startswith("approved_") else [],
        "prohibited_uses": ["training", "locked_test", "d4_acoustic_distress"],
        "unresolved_questions": [], "ext_decision": "TEST APPROVED" if review_status.startswith("approved_") else "none",
    })
    reg = {"schema_version": real["schema_version"], "description": "TEST ONLY", "datasets": [record]}
    assert not gov.validate_registry(reg), gov.validate_registry(reg)
    return reg


class NoRoot(unittest.TestCase):
    """Every test runs with SAHAY_DATASETS_ROOT removed from the environment."""

    def setUp(self):
        self._env = mock.patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop(gov.ROOT_ENV, None)
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()
        self._env.stop()


class Corpus(NoRoot):
    def setUp(self):
        super().setUp()
        self.rel = "text/fictional/corpus.csv"
        self.src = self.root / self.rel
        write_csv(self.src, ROWS)
        self.reg = fictional_registry(self.rel, self.src)

    def convert(self, **kw):
        return xc.convert(self.root, DATASET_ID, registry=self.reg, spec=SPEC, **kw)

    def records(self):
        return xc.load_normalized(self.root, DATASET_ID, self.reg)


# --- root and confinement ------------------------------------------------------------------------


class TestRoot(NoRoot):
    def test_missing_root_is_a_configuration_error(self):
        with self.assertRaises(gov.DatasetRootError):
            gov.dataset_root()
        self.assertEqual(inv.main(["--out", str(self.root / "o")]), inv.EXIT_CONFIG)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(xc.main(["convert", "--dataset", "dreaddit"]), 4)

    def test_paths_cannot_escape_the_root(self):
        for bad in ("../escape.csv", "/etc/passwd", "C:/Windows/x", "a/../../b"):
            with self.assertRaises(gov.DatasetRootError):
                gov.resolve_under(self.root, bad)

    def test_output_is_refused_inside_a_git_worktree(self):
        with self.assertRaises(xc.AdapterRefused):
            xc.output_dir(REPO, DATASET_ID, "0" * 64)

    def test_invalid_exclude_pattern_is_a_configuration_error(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(inv.main(["--root", str(self.root), "--exclude-pattern", "("]), inv.EXIT_CONFIG)


# --- governance gate ------------------------------------------------------------------------------


class TestGovernanceGate(Corpus):
    def test_a_licence_pending_dataset_is_refused_before_any_row_is_read(self):
        pending = fictional_registry(self.rel, self.src, review_status="licence_pending")
        with mock.patch.object(xc, "read_rows", side_effect=AssertionError("a row was read")):
            with self.assertRaises(xc.AdapterRefused):
                xc.convert(self.root, DATASET_ID, registry=pending, spec=SPEC)
        self.assertFalse((self.root / "normalized").exists())

    def test_every_real_dataset_is_refused(self):
        real = gov.load_registry()
        for rec in real["datasets"]:
            with self.assertRaises(xc.AdapterRefused, msg=rec["id"]):
                xc.convert(self.root, rec["id"], registry=real)

    def test_an_unverified_ontology_is_refused(self):
        spec = dict(SPEC, ontology_verified=False)
        with self.assertRaises(xc.AdapterRefused):
            xc.convert(self.root, DATASET_ID, registry=self.reg, spec=spec)

    def test_an_integrity_mismatch_is_refused(self):
        self.src.write_text(self.src.read_text(encoding="utf-8") + "x,happy,train\n", encoding="utf-8")
        with self.assertRaises(xc.AdapterRefused):
            self.convert()

    def test_the_real_specs_are_well_formed_and_blocked(self):
        for dataset_id, spec in xc.SPECS.items():
            self.assertEqual(xc.validate_spec(spec), [], dataset_id)
            self.assertIn(dataset_id, [r["id"] for r in gov.load_registry()["datasets"]])

    def test_a_raw_label_named_like_a_sahay_category_is_rejected(self):
        spec = dict(SPEC, label_families={"crisis_self_harm": "other"})
        self.assertTrue(any("collides" in e for e in xc.validate_spec(spec)))


# --- conversion ---------------------------------------------------------------------------------


class TestConversion(Corpus):
    def test_conversion_is_deterministic_and_idempotent(self):
        first = self.convert()
        self.assertEqual(first["status"], "written")
        body = (self.root / "normalized" / DATASET_ID / self.reg["datasets"][0]["sha256"][:12]
                / "records.jsonl").read_bytes()
        second = self.convert()
        self.assertEqual(second["status"], "unchanged")
        self.assertEqual(first["records_sha256"], second["records_sha256"])
        again = xc.convert_rows(DATASET_ID, self.reg["datasets"][0], SPEC, "f" * 64,
                                xc.read_rows(self.src, SPEC))
        again2 = xc.convert_rows(DATASET_ID, self.reg["datasets"][0], SPEC, "f" * 64,
                                 xc.read_rows(self.src, SPEC))
        self.assertEqual(again, again2)
        self.assertTrue(body)

    def test_ids_are_opaque_stable_and_external(self):
        self.convert()
        for r in self.records():
            self.assertRegex(r["record_id"], r"^EXT:fictional_test_corpus:(train|test|validation|unsplit):[0-9a-f]{16}$")
            self.assertEqual(len(r["source_row_sha256"]), 64)
            self.assertNotIn("bus", r["record_id"])

    def test_every_required_field_is_present(self):
        self.convert()
        required = {"record_id", "dataset_id", "dataset_version", "source_split", "source_row_sha256",
                    "language", "script", "raw_source_label", "source_label_category", "derivation",
                    "privacy_findings", "contamination", "permitted_evaluation_purposes",
                    "independently_authored", "independently_authored_statement", "locked_corpus_eligible",
                    "locked_corpus_statement"}
        for r in self.records():
            self.assertTrue(required <= set(r), required - set(r))
            self.assertTrue("text" in r or "turns" in r)

    def test_source_splits_are_preserved_and_never_called_a_holdout(self):
        self.convert()
        splits = {r["source_split"] for r in self.records()}
        self.assertEqual(splits, {"train", "test"})
        for r in self.records():
            self.assertNotIn("holdout", r["split_note"].replace("not a SAHAY holdout", ""))

    def test_unsupported_labels_and_splits_are_excluded_with_reasons(self):
        result = self.convert()
        self.assertEqual(result["excluded"].get("unsupported_source_label"), 1)
        self.assertEqual(result["excluded"].get("unsupported_split"), 1)

    def test_source_labels_stay_namespaced_source_metadata(self):
        self.convert()
        for r in self.records():
            for category in r["source_label_category"]:
                self.assertTrue(category.startswith("source:fictional_test_corpus:"))
                self.assertFalse(fw.is_sahay_category(category))
            self.assertFalse(r["sahay_mapping"]["applied"])

    def test_script_is_counted_not_guessed(self):
        self.assertEqual(xc.script_of("form"), "latin")
        self.assertEqual(xc.script_of("\u092b\u093e\u0930\u094d\u092e"), "devanagari")
        self.assertEqual(xc.script_of("form \u092b\u093e\u0930\u094d\u092e"), "mixed")
        self.assertEqual(xc.script_of("1234 !!"), "none")

    def test_an_unknown_row_language_stays_unknown(self):
        self.assertEqual(xc.normalise_language("klingon"), "unknown")
        self.assertEqual(xc.normalise_language("Hinglish"), "hinglish")


# --- malformed input ----------------------------------------------------------------------------


class TestMalformedInput(NoRoot):
    rec = {"version": "test-1", "approved_uses": ["research"]}

    def run_rows(self, path, spec):
        return xc.convert_rows(DATASET_ID, self.rec, spec, "a" * 64, xc.read_rows(path, spec))

    def test_malformed_csv_rows_are_excluded_not_raised(self):
        path = self.root / "bad.csv"
        path.write_text('text,mood,split\n"fine sentence about a form",happy,train\nonly-one-column\n\n'
                        '"",happy,train\n', encoding="utf-8")
        result = self.run_rows(path, SPEC)
        self.assertEqual(len(result["records"]), 1)
        self.assertEqual(result["excluded"], {"blank_row": 1, "column_count_mismatch": 1, "empty_text": 1})

    def test_undecodable_bytes_are_excluded(self):
        path = self.root / "bytes.csv"
        path.write_bytes(b"text,mood,split\nfine words about weather,happy,train\n\xff\xfe broken,happy,train\n")
        result = self.run_rows(path, SPEC)
        self.assertEqual(result["excluded"].get("encoding_error"), 1)

    def test_an_empty_csv_is_a_malformed_source(self):
        path = self.root / "empty.csv"
        path.write_text("", encoding="utf-8")
        with self.assertRaises(xc.MalformedSource):
            self.run_rows(path, SPEC)

    def test_malformed_jsonl_lines_are_excluded(self):
        path = self.root / "bad.jsonl"
        path.write_text('{"text": "a fine line about a bus", "mood": "happy"}\n{not json\n[1,2]\n'
                        '{"mood": "sad"}\n', encoding="utf-8")
        spec = dict(SPEC, format="jsonl", split_column=None)
        result = self.run_rows(path, spec)
        self.assertEqual(len(result["records"]), 1)
        self.assertEqual(result["excluded"], {"empty_text": 1, "invalid_json": 1, "json_not_an_object": 1})

    def test_text_files_become_one_record_per_line(self):
        path = self.root / "lines.txt"
        path.write_text("first line about a timetable\n\nsecond line about a form\n", encoding="utf-8")
        spec = dict(SPEC, format="txt", label_column=None, split_column=None, label_families={})
        result = self.run_rows(path, spec)
        self.assertEqual(len(result["records"]), 2)
        self.assertEqual(result["excluded"], {"blank_row": 1})

    def test_errors_never_quote_content(self):
        path = self.root / "empty.csv"
        path.write_text("", encoding="utf-8")
        try:
            self.run_rows(path, SPEC)
        except xc.MalformedSource as exc:
            self.assertNotIn("bus", str(exc))


# --- dialogues ----------------------------------------------------------------------------------


class TestDialogues(NoRoot):
    SPEC = {"format": "dialogue_csv", "text_column": "utterance", "label_column": "emotions",
            "dialogue_column": "dialogueId", "turn_column": "utterance_no", "speaker_column": "authorRole",
            "split_column": None, "language": "hi", "language_column": None, "multi_label": True,
            "label_families": {"Sad": "emotion", "Hopeful": "emotion", "Neutral": "emotion"},
            "ontology_verified": True, "ontology_evidence": "fictional"}

    def test_turns_are_grouped_and_ordered_by_source_turn_number(self):
        path = self.root / "dialogue.csv"
        write_csv(path, [("d2", "2", "agent", "second turn of dialogue two", "Neutral"),
                         ("d1", "3", "client", "third turn of dialogue one", "Hopeful"),
                         ("d1", "1", "client", "first turn of dialogue one", "Sad"),
                         ("d1", "2", "agent", "second turn of dialogue one", "Neutral,Hopeful"),
                         ("d2", "1", "client", "first turn of dialogue two", "Sad")],
                  header=("dialogueId", "utterance_no", "authorRole", "utterance", "emotions"))
        result = xc.convert_rows(DATASET_ID, {"version": "t", "approved_uses": []}, self.SPEC, "b" * 64,
                                 xc.read_rows(path, self.SPEC))
        self.assertEqual(len(result["records"]), 2)
        by_first = {r["turns"][0]["text"]: r for r in result["records"]}
        d1 = by_first["first turn of dialogue one"]
        self.assertEqual([t["source_turn_number"] for t in d1["turns"]], [1, 2, 3])
        self.assertEqual([t["turn_index"] for t in d1["turns"]], [0, 1, 2])
        self.assertEqual(d1["turns"][1]["source_label_category"],
                         ["source:fictional_test_corpus:Neutral", "source:fictional_test_corpus:Hopeful"])
        self.assertEqual(d1["d4"]["available"], False)

    def test_a_dialogue_with_a_bad_turn_is_excluded_whole(self):
        path = self.root / "dialogue.csv"
        write_csv(path, [("d1", "1", "client", "first turn text here", "Sad"),
                         ("d1", "2", "agent", "second turn text here", "Furious")],
                  header=("dialogueId", "utterance_no", "authorRole", "utterance", "emotions"))
        result = xc.convert_rows(DATASET_ID, {"version": "t", "approved_uses": []}, self.SPEC, "b" * 64,
                                 xc.read_rows(path, self.SPEC))
        self.assertEqual(result["records"], [])
        self.assertEqual(result["excluded"], {"unsupported_source_label": 1})


# --- duplicates and contamination -----------------------------------------------------------------


class TestDuplicatesAndContamination(Corpus):
    def test_exact_and_near_duplicates_are_marked(self):
        self.convert()
        kinds = sorted(r["duplicate_kind"] for r in self.records() if r["duplicate_kind"])
        self.assertEqual(kinds, ["exact", "near"])
        originals = {r["record_id"] for r in self.records()}
        for r in self.records():
            if r["duplicate_of"]:
                self.assertIn(r["duplicate_of"], originals)

    def test_cross_dataset_overlap_is_found(self):
        a = [{"record_id": "EXT:a:train:1", "exact_key": "k1", "near_key": None},
             {"record_id": "EXT:a:train:2", "exact_key": "k2", "near_key": "n2"}]
        b = [{"record_id": "EXT:b:test:9", "exact_key": "k1", "near_key": None},
             {"record_id": "EXT:b:test:8", "exact_key": "k8", "near_key": "n2"}]
        overlap = xc.cross_dataset_overlap({"a": a, "b": b})
        self.assertEqual({o["kind"] for o in overlap}, {"exact", "near"})
        self.assertTrue(all(o["datasets"] == ["a", "b"] for o in overlap))

    def test_a_copy_of_an_exposed_fixture_is_flagged(self):
        dev = json.loads((ML / "eval" / "corpus" / "dev.json").read_text(encoding="utf-8"))["samples"][0]
        fixture = next(t["text"] for t in dev["turns"] if t["speaker"] == "victim")
        path = self.root / "copy.csv"
        write_csv(path, [(fixture.upper(), "happy", "train")])
        result = xc.convert_rows(DATASET_ID, {"version": "t", "approved_uses": []}, SPEC, "c" * 64,
                                 xc.read_rows(path, SPEC))
        status = result["records"][0]["contamination"]
        self.assertEqual(status["status"], "exposed_overlap")
        self.assertIn(dev["id"], {f["matched_id"] for f in status["findings"]})
        self.assertFalse(status["locked_corpus_eligible"])

    def test_clean_fictional_text_finds_no_overlap(self):
        self.convert()
        first = next(r for r in self.records() if r["source_split"] == "train" and not r["duplicate_of"])
        self.assertEqual(first["contamination"]["status"], "no_overlap_found")


# --- privacy ------------------------------------------------------------------------------------


class TestPrivacy(Corpus):
    def test_identifiers_are_redacted_and_reported_by_rule_name_only(self):
        self.convert()
        texts = " ".join(r.get("text", "") for r in self.records())
        for leaked in ("example.invalid", "a.b@", "u/fictional_user", "@fictional_handle", "https://"):
            self.assertNotIn(leaked, texts)
        rules = {f["rule"] for r in self.records() for f in r["privacy_findings"]}
        self.assertTrue({"url", "email", "reddit_user", "social_handle"} <= rules)
        blob = json.dumps([r["privacy_findings"] for r in self.records()])
        self.assertNotIn("example", blob)
        self.assertNotIn("fictional_user", blob)

    def test_redaction_counts_rules(self):
        clean, counts = xc.redact("see www.x.invalid and http://y.invalid and call 9876543210")
        self.assertEqual(counts, {"url": 2, "phone": 1})
        self.assertNotIn("9876543210", clean)


# --- the label firewall -----------------------------------------------------------------------------


class TestLabelFirewall(unittest.TestCase):
    REQUIRED = [("stress", "crisis_self_harm"), ("depression", "diagnosis"),
                ("suicide_related", "immediate_danger"), ("sentiment_negative", "svi"),
                ("emotion_intensity", "svi"), ("emotion", "D4"), ("hate_speech", "continuing_threat"),
                ("sentiment_neutral", "safe"), ("sentiment_positive", "no_alert")]

    def good_record(self, family, target):
        return {"mapping_id": "MAP-EXT-001", "dataset_id": DATASET_ID,
                "source_category": f"source:{DATASET_ID}:x", "source_family": family, "sahay_target": target,
                "reviewer": "fictional-reviewer", "reviewer_role": "Safety lead (fictional)",
                "reasoning": "A fictional reviewer explains at length why this mapping might be considered.",
                "provenance": "fictional test", "timestamp": TS, "attestation": fw.MAPPING_ATTESTATION}

    def test_every_required_equivalence_is_refused_even_with_a_valid_record(self):
        for family, target in self.REQUIRED:
            with self.assertRaises(fw.LabelFirewallError, msg=f"{family}->{target}"):
                fw.map_to_sahay(family, target, self.good_record(family, target))

    def test_no_automatic_mapping_without_a_human_record(self):
        with self.assertRaises(fw.LabelFirewallError) as ctx:
            fw.map_to_sahay("other", "legal_urgency")
        self.assertIn("human mapping record", str(ctx.exception))

    def test_a_well_formed_record_is_still_not_authorised(self):
        record = self.good_record("other", "legal_urgency")
        self.assertEqual(fw.validate_mapping_record(record), [])
        with self.assertRaises(fw.LabelFirewallError) as ctx:
            fw.map_to_sahay("other", "legal_urgency", record)
        self.assertIn("not been approved", str(ctx.exception))
        self.assertEqual(fw.AUTHORISED_MAPPINGS, ())

    def test_an_ai_or_placeholder_reviewer_is_refused(self):
        for name in ("claude", "TODO-reviewer", "mapping-bot", "gpt-helper"):
            record = self.good_record("other", "legal_urgency")
            record["reviewer"] = name
            self.assertTrue(fw.validate_mapping_record(record), name)

    def test_d4_svi_band_and_diagnosis_are_never_populated_from_text(self):
        for target in ("D4", "svi", "band", "diagnosis"):
            with self.assertRaises(fw.LabelFirewallError):
                fw.map_to_sahay("other", target, self.good_record("other", target))

    def test_source_categories_are_namespaced(self):
        self.assertEqual(fw.source_category("ds", "non-suicide"), "source:ds:non-suicide")
        self.assertFalse(fw.is_sahay_category(fw.source_category("ds", "crisis_self_harm")))


# --- locked set, D4 and SVI -------------------------------------------------------------------------


class TestNeverEligible(Corpus):
    def test_no_external_record_can_enter_the_locked_set(self):
        self.convert()
        for r in self.records():
            self.assertFalse(r["locked_corpus_eligible"])
            self.assertFalse(r["independently_authored"])
            if r["source_split"] in ("train", "validation", "test"):
                violations = ct.check_assignments({"locked": [r["record_id"]]})
                self.assertTrue(violations)
        for rec in gov.load_registry()["datasets"]:
            self.assertFalse(rec["official_locked_test_allowed"])
            with self.assertRaises(gov.GovernanceError):
                gov.assert_can_be_locked_test(gov.load_registry(), rec["id"])

    def test_d4_is_structurally_unavailable_and_never_populated(self):
        self.convert()
        for r in self.records():
            self.assertEqual(r["d4"]["available"], False)
        for rec in gov.load_registry()["datasets"]:
            with self.assertRaises(gov.GovernanceError):
                gov.assert_can_populate_dimension(gov.load_registry(), rec["id"], "D4")

    def test_no_svi_or_band_is_ever_derived(self):
        self.convert()
        for r in self.records():
            blob = json.dumps(r)
            for key in ('"svi"', '"band"', '"svi_score"', '"dimensions"'):
                self.assertNotIn(key, blob)

    def test_the_locked_corpus_file_is_never_written(self):
        locked = ML / "eval" / "corpus" / "locked.json"
        before = locked.read_bytes()
        self.convert()
        self.assertEqual(locked.read_bytes(), before)
        self.assertEqual(json.loads(before.decode("utf-8"))["samples"], [])


# --- extraction ---------------------------------------------------------------------------------


def make_zip(path: Path, members) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            zf.writestr(name, data)


class TestExtraction(NoRoot):
    def registry_for(self, rel, status):
        path = self.root / rel
        reg = fictional_registry(rel, path, review_status=status)
        reg["datasets"][0]["archive_safety_status"] = "passed"
        reg["datasets"][0]["extraction_status"] = "not_extracted"
        return reg

    def test_permitted_extraction_writes_beneath_the_root(self):
        rel = "archives/good.zip"
        (self.root / "archives").mkdir()
        make_zip(self.root / rel, [("data/a.csv", "text,mood\nfictional line,happy\n")])
        result = audit.extract(self.registry_for(rel, "approved_for_research"), self.root, DATASET_ID)
        self.assertEqual(result["members"], 1)
        extracted = list((self.root / "extracted" / DATASET_ID).rglob("a.csv"))
        self.assertEqual(len(extracted), 1)

    def test_refused_extraction_writes_nothing(self):
        rel = "archives/good.zip"
        (self.root / "archives").mkdir()
        make_zip(self.root / rel, [("data/a.csv", "x")])
        with self.assertRaises(gov.GovernanceError):
            audit.extract(self.registry_for(rel, "licence_pending"), self.root, DATASET_ID)
        self.assertFalse((self.root / "extracted").exists())

    def test_an_unsafe_zip_is_refused(self):
        path = self.root / "evil.zip"
        make_zip(path, [("../escape.txt", "x"), ("ok/run.exe", "x"), ("inner.zip", "x")])
        report = az.inspect_zip(path)
        self.assertFalse(report["safe"])
        joined = " ".join(report["findings"])
        for finding in ("path_traversal", "executable_looking_member_names", "nested_archives_unsupported"):
            self.assertIn(finding, joined)
        with self.assertRaises(az.UnsafeArchive):
            az.safe_extract(path, self.root / "out")
        self.assertFalse((self.root / "out").exists())

    def test_no_partial_extraction_when_the_ceiling_is_crossed_mid_stream(self):
        path = self.root / "big.zip"
        make_zip(path, [("a.txt", "x" * 4000), ("b.txt", "y" * 4000)])
        dest = self.root / "out"
        with mock.patch.object(az, "inspect_zip", return_value={"safe": True, "findings": [], "members": 2}):
            with self.assertRaises(az.UnsafeArchive):
                az.safe_extract(path, dest, max_total=5000)
        self.assertFalse(dest.exists())
        self.assertEqual([p.name for p in self.root.iterdir() if p.name.startswith(".out")], [])

    def test_extraction_refuses_a_non_empty_destination(self):
        path = self.root / "good.zip"
        make_zip(path, [("a.txt", "x")])
        dest = self.root / "out"
        dest.mkdir()
        (dest / "existing.txt").write_text("keep", encoding="utf-8")
        with self.assertRaises(az.UnsafeArchive):
            az.safe_extract(path, dest)
        self.assertEqual((dest / "existing.txt").read_text(encoding="utf-8"), "keep")

    def test_a_zip_renamed_to_csv_is_still_inspected_by_the_audit(self):
        path = self.root / "looks.csv"
        make_zip(path, [("../escape.txt", "x")])
        rec = {"archive_safety_status": "not_applicable"}
        self.assertFalse(audit.archive_check(path, rec)["safe"])

    def test_a_loose_file_is_not_an_archive_only_when_registered_so(self):
        path = self.root / "loose.csv"
        path.write_text("text\nfine\n", encoding="utf-8")
        self.assertTrue(audit.archive_check(path, {"archive_safety_status": "not_applicable"})["safe"])
        self.assertFalse(audit.archive_check(path, {"archive_safety_status": "passed"})["safe"])


# --- inventory ----------------------------------------------------------------------------------


class TestInventory(NoRoot):
    def test_inventory_records_metadata_and_never_content(self):
        write_csv(self.root / "a" / "data.csv", [("a fictional row about a timetable", "happy", "train")])
        (self.root / "b").mkdir()
        (self.root / "b" / "clip.wav").write_bytes(b"version https://git-lfs.github.com/spec/v1\noid sha256:0\n")
        make_zip(self.root / "c.zip", [("../x.txt", "y")])
        report = inv.build(self.root, registry=gov.load_registry())
        blob = json.dumps(report)
        self.assertNotIn("fictional row", blob)
        rows = {r["relative_path"]: r for r in report["files"]}
        self.assertEqual(rows["a/data.csv"]["csv"]["columns"], ["text", "mood", "split"])
        self.assertTrue(rows["b/clip.wav"]["git_lfs_pointer"])
        self.assertFalse(rows["c.zip"]["zip"]["safe"])
        self.assertEqual(report["root"], "<SAHAY_DATASETS_ROOT>")

    def test_a_data_like_first_line_is_withheld(self):
        path = self.root / "noheader.csv"
        path.write_text("This is a whole sentence about a bus, with punctuation.,1\n", encoding="utf-8")
        result = inv.csv_columns(path)
        self.assertEqual(result["header"], "withheld")
        self.assertNotIn("bus", json.dumps(result))

    def test_excluded_paths_are_never_opened_or_named(self):
        (self.root / "out_of_scope").mkdir()
        (self.root / "out_of_scope" / "private.csv").write_text("secret,row\n", encoding="utf-8")
        (self.root / "in.csv").write_text("text\nfine\n", encoding="utf-8")
        opened = []
        real_open = open

        def spy(file, *a, **k):
            opened.append(str(file))
            return real_open(file, *a, **k)

        with mock.patch("builtins.open", spy):
            report = inv.build(self.root, [re.compile("out_of_scope")], registry=gov.load_registry())
        self.assertNotIn("out_of_scope", json.dumps(report))
        self.assertFalse(any("out_of_scope" in p for p in opened))

    def test_inventory_output_is_refused_inside_the_repository(self):
        (self.root / "in.csv").write_text("text\nfine\n", encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(inv.main(["--root", str(self.root), "--out", str(REPO / "ml" / "x")]),
                             inv.EXIT_CONFIG)
        self.assertFalse((REPO / "ml" / "x").exists())

    def test_inventory_defaults_to_the_private_reports_directory(self):
        (self.root / "in.csv").write_text("text\nfine\n", encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(inv.main(["--root", str(self.root)]), inv.EXIT_OK)
        self.assertTrue((self.root / "reports" / "inventory" / "inventory.json").is_file())
        report = json.loads((self.root / "reports" / "inventory" / "inventory.json").read_text(encoding="utf-8"))
        self.assertFalse(any(r["relative_path"].startswith("reports/") for r in report["files"]))

    def test_git_lfs_pointer_stubs_are_never_counted_as_media(self):
        (self.root / "clips").mkdir()
        for i in range(3):
            (self.root / "clips" / f"c{i}.wav").write_bytes(
                b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"0" * 64 + b"\nsize 1\n")
        report = inv.build(self.root, registry=gov.load_registry())
        media = inv.media_availability(report, "clips")
        self.assertEqual((media["media_files"], media["git_lfs_pointer_stubs"], media["real_media_files"]), (3, 3, 0))
        self.assertFalse(media["available"])
        self.assertNotIn("crema_d", xc.SPECS)  # no audio adapter exists, so no acoustic result can be produced


# --- report ---------------------------------------------------------------------------------------


class TestReport(Corpus):
    def test_the_registry_only_report_needs_no_dataset_root(self):
        report = xr.build(None)
        text = xr.render(report)
        self.assertFalse(report["pipeline_run"])
        self.assertFalse(report["tuning_performed"])
        self.assertEqual(sum(r["conversion_permitted_by_registry"] for r in report["datasets"]), 0)
        self.assertIn("Private exploratory research composition", text)

    def test_the_report_composes_converted_records_without_text(self):
        self.convert()
        report = xr.build(self.root, registry=self.reg)
        row = report["datasets"][0]
        comp = row["composition"]
        self.assertEqual(comp["records"], 6)
        self.assertEqual(comp["source_splits"], {"test": 2, "train": 4})
        self.assertEqual(comp["duplicates"], {"exact": 1, "near": 1})
        self.assertEqual(comp["locked_corpus_eligible"], 0)
        self.assertEqual(comp["d4_available"], 0)
        self.assertEqual(comp["records_requiring_human_mapping"], 6)
        blob = json.dumps(report) + xr.render(report)
        for text, _, _ in ROWS:
            self.assertNotIn(text[:20], blob)

    def test_forbidden_wording_is_caught(self):
        for bad in ("Official results", "an independent benchmark", "validated model", "clinical  accuracy",
                    "Production Accuracy"):
            with self.assertRaises(xr.WordingError, msg=bad):
                xr.assert_wording(bad)
        xr.assert_wording("exploratory research composition; not blind-authored")

    def test_the_analysis_label_is_fixed(self):
        self.assertEqual(xr.ANALYSIS_LABEL, "external_exploratory_analysis")
        self.assertEqual(xr.REPORT_LABEL, "external_exploratory_composition")
        xr.assert_wording(xr.ANALYSIS_LABEL)

    def test_the_cli_prints_no_content(self):
        self.convert()
        buf = io.StringIO()
        with redirect_stdout(buf):
            xc.main(["--root", str(self.root), "specs"])
            xr.main(["--root", str(self.root), "--out", str(self.root / "report")])
        out = buf.getvalue() + (self.root / "report" / "report.md").read_text(encoding="utf-8")
        for text, _, _ in ROWS:
            self.assertNotIn(text[:20], out)


# --- registry ------------------------------------------------------------------------------------


class TestRegistry(unittest.TestCase):
    def setUp(self):
        self.reg = gov.load_registry()

    def test_the_registry_validates_and_approves_nothing_external(self):
        self.assertEqual(gov.validate_registry(self.reg), [])
        for rec in self.reg["datasets"]:
            self.assertFalse(rec["review_status"].startswith("approved_"), rec["id"])
            self.assertEqual(rec["approved_uses"], [], rec["id"])
            self.assertEqual(rec["sahay_dimension_mappings"], {}, rec["id"])

    def test_new_datasets_are_registered_once_and_existing_ones_not_duplicated(self):
        ids = [r["id"] for r in self.reg["datasets"]]
        self.assertEqual(len(ids), len(set(ids)))
        for new in ("reddit_suicide_detection", "hinglish_hate_speech_local_derivative"):
            self.assertIn(new, ids)
            self.assertTrue((ML / "data" / "cards" / f"{new}.md").is_file())
        self.assertEqual(sum(1 for i in ids if "dreaddit" in i), 1)
        self.assertEqual(sum(1 for i in ids if "emoinhindi" in i), 1)

    def test_every_downloaded_record_stays_before_licence_approval(self):
        for rec in self.reg["datasets"]:
            if rec["download_status"] == "downloaded":
                self.assertEqual(rec["review_status"], "licence_pending", rec["id"])

    def test_no_machine_path_enters_the_registry(self):
        blob = json.dumps(self.reg).replace("https://", "").replace("http://", "")
        self.assertIsNone(re.search(r"[A-Za-z]:[\\/]|^/(home|Users|mnt)/", blob, re.M))
        for rec in self.reg["datasets"]:
            rel = rec["local_relative_path"]
            if rel:
                self.assertTrue(gov.safe_relative(rel), rec["id"])


# --- isolation --------------------------------------------------------------------------------------


class TestIsolation(unittest.TestCase):
    APP_DIRS = ("assessment.py", "dialogue", "guardrails", "svi", "nlp", "asr", "tts", "acoustics", "eval")

    def test_no_application_module_imports_external_data(self):
        pattern = re.compile(r"^\s*(from|import)\s+(ml\.data|\.\.data|\.data)\b", re.M)
        offenders = []
        for path in iter_source_files(ML):
            rel = path.relative_to(ML).as_posix()
            if rel.startswith(("data/", "tests/")):
                continue
            if pattern.search(path.read_text(encoding="utf-8")):
                offenders.append(rel)
        self.assertEqual(offenders, [])

    def test_the_intake_modules_import_no_prediction_or_scoring_module(self):
        banned = re.compile(r"^\s*(from|import)\s+\S*(assessment|detectors|svi|crisis_precheck|validator|"
                            r"recommend|predict|checks)\b", re.M)
        for name in ("external_corpus.py", "external_report.py", "label_firewall.py", "inventory.py"):
            text = (ML / "data" / name).read_text(encoding="utf-8")
            self.assertIsNone(banned.search(text), name)

    def test_no_messaging_export_path_or_parser_exists(self):
        word = "whats" + "app"
        for base in (ML, REPO / "data-scripts"):
            for path in iter_source_files(base, "*"):
                if path.suffix in (".py", ".md", ".json", ".txt", ".ps1"):
                    self.assertNotIn(word, path.read_text(encoding="utf-8", errors="ignore").casefold(),
                                     path.relative_to(REPO).as_posix())

    def test_the_suite_needs_no_dataset_root_and_touches_no_network(self):
        from ml.eval import checks
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(gov.ROOT_ENV, None)
            with tempfile.TemporaryDirectory() as tmp, checks.offline() as net:
                root = Path(tmp)
                rel = "c.csv"
                write_csv(root / rel, ROWS[:2])
                reg = fictional_registry(rel, root / rel)
                xc.convert(root, DATASET_ID, registry=reg, spec=SPEC)
                xr.build(root, registry=reg)
                inv.build(root, registry=reg)
        self.assertTrue(net["ok"], net)


# --- the local exploratory research override ---------------------------------------------------------------------------


class OverrideCorpus(NoRoot):
    """A fictional licence_pending dataset: refused by default, eligible for the override."""

    def setUp(self):
        super().setUp()
        self.rel = "text/fictional/corpus.csv"
        self.src = self.root / self.rel
        write_csv(self.src, ROWS)
        self.reg = fictional_registry(self.rel, self.src, review_status="licence_pending")
        self.override = xc.make_override(xc.OVERRIDE_ACKNOWLEDGEMENT, "fictional-operator")

    def convert(self, override="default"):
        return xc.convert(self.root, DATASET_ID, registry=self.reg, spec=SPEC,
                          override=self.override if override == "default" else override)


class TestOverride(OverrideCorpus):
    def test_the_default_path_still_refuses_licence_pending(self):
        with self.assertRaises(xc.AdapterRefused):
            self.convert(override=None)
        self.assertFalse((self.root / "normalized").exists())

    def test_the_override_needs_the_exact_acknowledgement(self):
        for ack in ("", "yes", xc.OVERRIDE_ACKNOWLEDGEMENT.upper(), xc.OVERRIDE_ACKNOWLEDGEMENT[:-1]):
            with self.assertRaises(xc.AdapterRefused, msg=ack):
                self.convert(override=xc.make_override(ack))
        self.assertFalse((self.root / "normalized").exists())

    def test_the_cli_needs_both_the_flag_and_the_acknowledgement(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(xc.main(["--root", str(self.root), "convert", "--dataset", "dreaddit",
                                      xc.OVERRIDE_FLAG]), 3)
            self.assertEqual(xc.main(["--root", str(self.root), "convert", "--dataset", "dreaddit",
                                      "--acknowledge", xc.OVERRIDE_ACKNOWLEDGEMENT]), 3)
        self.assertIn("refused", buf.getvalue())

    def test_the_override_converts_and_warns(self):
        result = self.convert()
        self.assertEqual(result["governance_basis"], "local_research_override")
        self.assertEqual(result["records"], 6)
        manifest = xc.load_manifest(self.root, DATASET_ID, self.reg)
        self.assertFalse(manifest["override"]["licence_approved"])
        self.assertIn("UNRESOLVED", manifest["override"]["warning"])
        for r in xc.load_normalized(self.root, DATASET_ID, self.reg):
            self.assertEqual(r["governance_basis"], "local_research_override")
            self.assertEqual(r["permitted_evaluation_purposes"], list(xc.OVERRIDE_PURPOSES))

    def test_every_override_use_is_recorded_in_the_private_log(self):
        self.convert()
        log = self.root / "reports" / "overrides" / "override-log.jsonl"
        entries = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(entries[-1]["event"], "local_research_override_conversion")
        self.assertFalse(entries[-1]["licence_approved"])
        self.assertEqual(entries[-1]["operator"], "fictional-operator")
        self.assertNotIn("bus pass", log.read_text(encoding="utf-8"))

    def test_the_cli_prints_the_warning(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            xc.override_from_args(mock.Mock(local_research_override=True, acknowledge=xc.OVERRIDE_ACKNOWLEDGEMENT,
                                            operator="x"))
        self.assertIn("Licensing and privacy approval for this dataset are UNRESOLVED", buf.getvalue())

    def test_the_override_is_limited_to_local_development_purposes(self):
        for purpose in xc.OVERRIDE_REFUSED_PURPOSES:
            with self.assertRaises(xc.AdapterRefused, msg=purpose):
                xc.authorise(self.reg, DATASET_ID, purpose, self.override)
        for purpose in ("research", "evaluation", "anything_else"):
            with self.assertRaises(xc.AdapterRefused, msg=purpose):
                xc.authorise(self.reg, DATASET_ID, purpose, self.override)
        for purpose in xc.OVERRIDE_PURPOSES:
            self.assertEqual(xc.authorise(self.reg, DATASET_ID, purpose, self.override)["basis"],
                             "local_research_override")

    def test_training_redistribution_locked_and_freeze_are_never_authorised(self):
        for purpose in ("training", "redistribution", "locked_test", "corpus_freeze", "blind_corpus_intake",
                        "independent_evaluation", "official_evaluation", "model_publication"):
            self.assertIn(purpose, xc.OVERRIDE_REFUSED_PURPOSES)
            with self.assertRaises(xc.AdapterRefused):
                xc.authorise(self.reg, DATASET_ID, purpose, self.override)
        for purpose in ("training", "evaluation", "research"):
            with self.assertRaises(gov.GovernanceError):
                gov.select_for(self.reg, DATASET_ID, purpose)
        with self.assertRaises(gov.GovernanceError):
            gov.assert_can_be_locked_test(self.reg, DATASET_ID)

    def test_the_override_cannot_lift_quarantine_or_rejection(self):
        for state in ("quarantined", "rejected"):
            reg = copy.deepcopy(self.reg)
            reg["datasets"][0]["review_status"] = state
            with self.assertRaises(xc.AdapterRefused, msg=state):
                xc.authorise(reg, DATASET_ID, "local_research_conversion", self.override)

    def test_the_override_cannot_write_into_a_sahay_checkout(self):
        fake = self.root / "checkout"
        (fake / ".git").mkdir(parents=True)
        (fake / "ml" / "data").mkdir(parents=True)
        (fake / "ml" / "data" / "governance.py").write_text("# marker", encoding="utf-8")
        rel = "checkout/data/c.csv"
        write_csv(self.root / rel, ROWS[:2])
        reg = fictional_registry(rel, self.root / rel, review_status="licence_pending")
        with self.assertRaises(xc.AdapterRefused):
            xc.convert(fake, DATASET_ID, registry=reg, spec=SPEC, override=self.override)
        self.assertTrue(xc.inside_sahay_worktree(REPO))
        self.assertTrue(xc.inside_sahay_worktree(REPO / "runtime"))

    def test_the_blind_corpus_freeze_and_evaluation_have_no_override(self):
        for name in ("blind_corpus.py", "blind_evaluation.py", "review_workflow.py"):
            text = (ML / "eval" / name).read_text(encoding="utf-8")
            self.assertNotIn("local_research_override", text, name)
            self.assertNotIn("external_corpus", text, name)
        for path in (ML / "eval" / "blind").glob("*.py"):
            self.assertNotIn("local_research_override", path.read_text(encoding="utf-8"), path.name)
        from ml.eval import blind_corpus
        with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                blind_corpus.main([xc.OVERRIDE_FLAG, "freeze", "--actor", "person-001"])

    def test_the_registry_is_not_changed_by_an_override(self):
        before = gov.REGISTRY_PATH.read_bytes()
        self.convert()
        self.assertEqual(gov.REGISTRY_PATH.read_bytes(), before)


class TestLocalCopies(OverrideCorpus):
    def copy_spec(self, sha=None, size=None):
        copy_rel = "loose/copy.csv"
        write_csv(self.root / copy_rel, ROWS[:3])
        real_sha = az.sha256_file(self.root / copy_rel)
        spec = dict(SPEC, local_copies=[{"relative_path": copy_rel, "sha256": sha or real_sha,
                                         "byte_size": size or (self.root / copy_rel).stat().st_size, "note": "t"}])
        self.src.unlink()  # the registered file is absent, as in the real root
        return spec, real_sha

    def test_a_documented_local_copy_is_used_when_the_registered_file_is_absent(self):
        spec, real_sha = self.copy_spec()
        self.reg["datasets"][0]["unresolved_questions"] = [f"a local copy exists with sha256 {real_sha}"]
        result = xc.convert(self.root, DATASET_ID, registry=self.reg, spec=spec, override=self.override)
        self.assertEqual(result["records"], 3)
        self.assertEqual(xc.load_manifest(self.root, DATASET_ID, self.reg)["source_file"], "documented_local_copy")

    def test_an_undocumented_local_copy_is_refused(self):
        spec, _ = self.copy_spec()
        with self.assertRaises(xc.AdapterRefused):
            xc.convert(self.root, DATASET_ID, registry=self.reg, spec=spec, override=self.override)

    def test_a_local_copy_with_the_wrong_hash_is_refused(self):
        spec, real_sha = self.copy_spec(sha="0" * 64)
        self.reg["datasets"][0]["unresolved_questions"] = ["a local copy exists with sha256 " + "0" * 64]
        with self.assertRaises(xc.AdapterRefused):
            xc.convert(self.root, DATASET_ID, registry=self.reg, spec=spec, override=self.override)

    def test_the_real_pinned_copies_are_documented_in_the_registry(self):
        reg = gov.load_registry()
        for dataset_id, spec in xc.SPECS.items():
            text = json.dumps(gov.get(reg, dataset_id))
            for copy_ in spec.get("local_copies") or []:
                self.assertIn(copy_["sha256"], text, dataset_id)
                self.assertTrue(gov.safe_relative(copy_["relative_path"]), dataset_id)


class TestStreaming(OverrideCorpus):
    def test_records_are_streamed_by_a_generator(self):
        gen = xc.iter_records(DATASET_ID, self.reg["datasets"][0], SPEC, "f" * 64,
                              xc.read_rows(self.src, SPEC), __import__("collections").Counter())
        self.assertTrue(hasattr(gen, "__next__"))
        self.assertIn("record_id", next(gen))

    def test_streaming_conversion_is_deterministic_and_idempotent(self):
        first = self.convert()
        second = self.convert()
        self.assertEqual(first["records_sha256"], second["records_sha256"])
        self.assertEqual(second["status"], "unchanged")
        with tempfile.TemporaryDirectory() as other:
            write_csv(Path(other) / self.rel, ROWS)
            third = xc.convert(Path(other), DATASET_ID, registry=self.reg, spec=SPEC, override=self.override)
        self.assertEqual(first["records_sha256"], third["records_sha256"])

    def test_no_partial_output_is_left_after_a_failure(self):
        with mock.patch.object(xc, "redact", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.convert()
        out = self.root / "normalized" / DATASET_ID
        leftovers = [p.name for p in out.rglob("*") if p.is_file()] if out.exists() else []
        self.assertEqual(leftovers, [])

    def test_a_headerless_file_uses_declared_columns(self):
        path = self.root / "noheader.csv"
        path.write_text("7,first fictional line about a form,1\n9,second fictional line about a bus,0\n",
                        encoding="utf-8")
        spec = dict(SPEC, header_columns=["idx", "text", "mood"], label_column="mood", split_column=None,
                    label_families={"1": "sentiment_unspecified", "0": "sentiment_unspecified"})
        result = xc.convert_rows(DATASET_ID, {"version": "t", "approved_uses": []}, spec, "d" * 64,
                                 xc.read_rows(path, spec))
        self.assertEqual(len(result["records"]), 2)

    def test_missing_labels_are_excluded_with_their_own_reason(self):
        path = self.root / "nolabel.csv"
        write_csv(path, [("a fictional line about a counter", "", "train"),
                         ("another fictional line about a queue", "happy", "train")])
        result = xc.convert_rows(DATASET_ID, {"version": "t", "approved_uses": []}, SPEC, "e" * 64,
                                 xc.read_rows(path, SPEC))
        self.assertEqual(result["excluded"], {"missing_source_label": 1})


# --- the exploratory regression -------------------------------------------------------------------


class TestSampling(unittest.TestCase):
    def recs(self, n, label="source:ds:a", split="unsplit"):
        return [{"record_id": f"EXT:ds:{split}:{i:016x}", "source_split": split, "source_label_category": [label],
                 "duplicate_of": None, "contamination": {"status": "no_overlap_found"}, "text": "x"}
                for i in range(n)]

    def test_sampling_is_deterministic_and_capped_per_stratum(self):
        data = self.recs(50, "source:ds:a") + self.recs(7, "source:ds:b")
        one, m1 = xg.sample(data, cap=10, seed="s")
        two, m2 = xg.sample(list(reversed(data)), cap=10, seed="s")
        self.assertEqual([r["record_id"] for r in one], [r["record_id"] for r in two])
        self.assertEqual(m1["strata"]["unsplit::source:ds:a"], {"available": 50, "sampled": 10})
        self.assertEqual(m1["strata"]["unsplit::source:ds:b"], {"available": 7, "sampled": 7})
        other, _ = xg.sample(data, cap=10, seed="another")
        self.assertNotEqual({r["record_id"] for r in one}, {r["record_id"] for r in other})

    def test_splits_are_never_pooled(self):
        data = self.recs(5, split="train") + self.recs(5, split="test")
        _, method = xg.sample(data, cap=3)
        self.assertEqual(set(method["strata"]), {"train::source:ds:a", "test::source:ds:a"})

    def test_duplicates_and_fixture_copies_are_left_out(self):
        data = self.recs(4)
        data[0]["duplicate_of"] = "EXT:ds:unsplit:x"
        data[1]["contamination"] = {"status": "exposed_overlap"}
        chosen, method = xg.sample(data, cap=10)
        self.assertEqual(len(chosen), 2)
        self.assertEqual(method["left_out"], {"duplicate": 1, "exposed_fixture_overlap": 1})

    def test_a_dialogue_is_sampled_under_its_most_frequent_label(self):
        record = {"turns": [{"source_label_category": ["source:e:sad"]}, {"source_label_category": ["source:e:joy"]},
                            {"source_label_category": ["source:e:sad", "source:e:joy"]},
                            {"source_label_category": ["source:e:sad"]}]}
        self.assertEqual(xg.stratum(record), "source:e:sad")

    def test_dialogue_speakers_keep_their_order(self):
        record = {"record_id": "EXT:e:unsplit:1", "turns": [
            {"speaker": "user", "text": "first"}, {"speaker": "bot", "text": "second"},
            {"speaker": "user", "text": "third"}]}
        sample, unmapped = xg.to_pipeline_sample(record)
        self.assertEqual([t["speaker"] for t in sample["turns"]], ["victim", "assistant", "victim"])
        self.assertEqual([t["text"] for t in sample["turns"]], ["first", "second", "third"])
        self.assertEqual(sample["channel"], "mobile_chat")
        self.assertEqual(unmapped, 0)


class TestExploratoryRun(OverrideCorpus):
    def setUp(self):
        super().setUp()
        self.convert()

    def run_it(self):
        return xg.run(self.root, self.override, [DATASET_ID], cap=10, registry=self.reg)

    def test_the_run_needs_the_override(self):
        with self.assertRaises(xc.AdapterRefused):
            xg.run(self.root, xc.make_override("no"), [DATASET_ID], registry=self.reg)
        with redirect_stdout(io.StringIO()):
            self.assertEqual(xg.main(["--root", str(self.root), "run", "--dataset", DATASET_ID]), 3)

    def test_the_run_is_labelled_and_reports_firing_rates_only(self):
        report = self.run_it()
        self.assertEqual(report["label"], "external_exploratory_analysis")
        self.assertEqual(report["result_kind"], "exploratory firing rates only")
        self.assertFalse(report["product_use_permitted"])
        self.assertFalse(report["privacy_approved"])
        self.assertFalse(report["licence_approved"])
        self.assertFalse(report["tuning_performed"])
        blob = json.dumps(report).lower()
        for word in ("precision", "recall", "\"f1\"", "accuracy"):
            self.assertNotIn(word, blob)
        res = report["datasets"][DATASET_ID]
        self.assertIn("crisis_precheck_firing_rate", res["overall"])
        self.assertTrue(all(k.split("::")[1].startswith("source:") for k in res["by_split_and_source_label"]))
        md = (self.root / "reports" / "external-analysis" / "external_exploratory_analysis.md"
              ).read_text(encoding="utf-8")
        self.assertIn("fired on", md)

    def test_d4_is_unavailable_for_every_text_record(self):
        res = self.run_it()["datasets"][DATASET_ID]
        self.assertEqual(res["overall"]["d4_unavailable_rate"], 1.0)
        self.assertEqual(res["overall"]["evidence_link_validity_rate"], 1.0)

    def test_no_narrative_appears_in_the_report_or_console(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            report = self.run_it()
        out = self.root / "reports" / "external-analysis"
        blob = buf.getvalue() + json.dumps(report) + "".join(p.read_text(encoding="utf-8") for p in out.glob("*"))
        for text, _, _ in ROWS:
            self.assertNotIn(text[:20], blob)

    def test_accuracy_keys_and_forbidden_wording_are_refused(self):
        with self.assertRaises(ValueError):
            xg.check_report({"datasets": {"x": {"precision": 0.5}}})
        with self.assertRaises(xr.WordingError):
            xg.check_report({"statement": "independent results"})
        with self.assertRaises(xr.WordingError):
            xr.assert_wording("locked-set performance")

    def test_the_run_is_recorded_in_the_override_log(self):
        self.run_it()
        log = (self.root / "reports" / "overrides" / "override-log.jsonl").read_text(encoding="utf-8")
        self.assertIn("local_research_override_exploratory_analysis", log)

    def test_the_intake_and_run_modules_keep_prediction_imports_lazy(self):
        text = (ML / "data" / "external_analysis.py").read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.startswith(("import ", "from ")):
                self.assertNotRegex(line, r"predict|assessment|detectors|svi")


# --- policy correction: research-only override, quarantine, sensitivity, product isolation ------------


class TestResearchOnlyPolicy(OverrideCorpus):
    def test_there_is_exactly_one_bypass_flag(self):
        self.assertEqual(xc.OVERRIDE_FLAG, "--local-research-override")
        with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
            with self.assertRaises(SystemExit):
                xc.main(["--root", str(self.root), "convert", "--dataset", "dreaddit", "--local-mvp-override",
                         "--acknowledge", xc.OVERRIDE_ACKNOWLEDGEMENT])
        for path in (ML / "data").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("local-mvp-override", text, path.name)
            self.assertNotIn("local_mvp", text, path.name)

    def test_the_acknowledgement_states_every_required_condition(self):
        ack = xc.OVERRIDE_ACKNOWLEDGEMENT.lower()
        for clause in ("licensing and privacy approval remain unresolved", "local offline",
                       "cannot enter the sahay product or demo", "training", "tuning", "official evaluation",
                       "publication", "i take responsibility for access to the private source files"):
            self.assertIn(clause, ack)

    def test_product_mvp_demo_and_tuning_purposes_are_refused_even_with_the_override(self):
        for purpose in ("mvp_product", "product", "demo", "victim_facing_output", "backend_ingestion",
                        "threshold_tuning", "lexicon_tuning", "model_tuning", "publication", "external_upload"):
            self.assertIn(purpose, xc.OVERRIDE_REFUSED_PURPOSES)
            with self.assertRaises(xc.AdapterRefused, msg=purpose):
                xc.authorise(self.reg, DATASET_ID, purpose, self.override)

    def test_the_override_never_bypasses_privacy_screening(self):
        calls = []
        real = xc.redact

        def spy(text):
            calls.append(1)
            return real(text)

        with mock.patch.object(xc, "redact", spy):
            self.convert()
        self.assertEqual(len(calls), 6)
        texts = " ".join(r.get("text", "") for r in xc.load_normalized(self.root, DATASET_ID, self.reg))
        self.assertNotIn("example.invalid", texts)

    def test_the_override_never_bypasses_private_root_confinement(self):
        with self.assertRaises(gov.DatasetRootError):
            xc.private_dir(self.root, "../outside")
        with self.assertRaises(xc.AdapterRefused):
            xc.private_dir(REPO, "normalized/x")

    def test_outputs_are_marked_quarantined_research_artefacts(self):
        self.convert()
        manifest = xc.load_manifest(self.root, DATASET_ID, self.reg)
        self.assertEqual(manifest["artifact_class"], "quarantined_research_artifact")
        self.assertIn("personal names", manifest["residual_identifier_risk"])
        self.assertIn("delete", manifest["retention_recommendation"])
        self.assertFalse(manifest["override"]["privacy_approved"])
        for r in xc.load_normalized(self.root, DATASET_ID, self.reg):
            self.assertEqual(r["research_artifact"]["class"], "quarantined_research_artifact")

    def test_the_retention_recommendation_is_private_and_deletes_nothing(self):
        self.convert()
        before = sorted(p.as_posix() for p in (self.root / "normalized").rglob("*") if p.is_file())
        record = xr.write_retention_recommendation(self.root)
        after = sorted(p.as_posix() for p in (self.root / "normalized").rglob("*") if p.is_file())
        self.assertEqual(before, after)
        self.assertFalse(record["automatic_deletion"])
        self.assertEqual(record["root"], "<SAHAY_DATASETS_ROOT>")
        self.assertTrue(all(not o["relative_path"].startswith(("/", "C:", "D:")) for o in record["outputs"]))
        self.assertTrue((self.root / "reports" / "retention" / "retention-recommendation.json").is_file())
        self.assertFalse(xc.inside_sahay_worktree(self.root / "reports" / "retention"))


class TestSensitivityFlags(unittest.TestCase):
    def setUp(self):
        self.reg = gov.load_registry()

    def test_the_registry_schema_carries_sensitivity_flags(self):
        self.assertEqual(self.reg["schema_version"], "1.1.0")
        for rec in self.reg["datasets"]:
            self.assertIsInstance(rec["sensitivity_flags"], list, rec["id"])

    def test_authentic_narrative_datasets_carry_all_four_flags(self):
        for dataset_id in ("dreaddit", "reddit_suicide_detection"):
            self.assertEqual(sorted(gov.get(self.reg, dataset_id)["sensitivity_flags"]),
                             sorted(gov.SENSITIVITY_FLAGS), dataset_id)
        for dataset_id in ("hinglish_hate_speech_local_derivative", "hinglish_sentiment_kaggle"):
            flags = gov.get(self.reg, dataset_id)["sensitivity_flags"]
            self.assertIn("real_user_generated_text", flags)
            self.assertIn("personal_names_not_reliably_redacted", flags)

    def test_victim_narratives_require_a_victim_facing_prohibition(self):
        rec = copy.deepcopy(gov.get(self.reg, "dreaddit"))
        rec["prohibited_uses"] = [u for u in rec["prohibited_uses"] if u != "victim_facing_output"]
        self.assertTrue(any("victim_facing_output" in e for e in gov.validate_record(rec)))

    def test_unknown_flags_are_refused(self):
        rec = copy.deepcopy(gov.get(self.reg, "dreaddit"))
        rec["sensitivity_flags"] = ["safe_to_use"]
        self.assertTrue(any("sensitivity flag" in e for e in gov.validate_record(rec)))


class TestProductIsolation(unittest.TestCase):
    PATTERN = re.compile(r"ml\.data|ml/data|external_corpus|external_analysis|external_report|"
                         r"SAHAY_DATASETS_ROOT|normalized/|records\.jsonl")

    def test_no_backend_frontend_or_mobile_module_touches_external_data(self):
        offenders = []
        for base in ("backend", "frontend", "mobile"):
            root = REPO / base
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                parts = set(path.parts)
                if not path.is_file() or parts & {"node_modules", ".venv", "venv", "dist", "build", ".expo",
                                                  "__pycache__"}:
                    continue
                if path.suffix not in (".py", ".ts", ".tsx", ".js", ".jsx", ".json", ".toml", ".cfg"):
                    continue
                if self.PATTERN.search(path.read_text(encoding="utf-8", errors="ignore")):
                    offenders.append(path.relative_to(REPO).as_posix())
        self.assertEqual(offenders, [])

    def test_no_ml_application_module_imports_the_external_modules(self):
        pattern = re.compile(r"^\s*(from|import)\s+\S*(external_corpus|external_analysis|external_report|"
                             r"label_firewall|inventory)\b", re.M)
        for path in iter_source_files(ML):
            rel = path.relative_to(ML).as_posix()
            if rel.startswith(("data/", "tests/")):
                continue
            self.assertIsNone(pattern.search(path.read_text(encoding="utf-8")), rel)


if __name__ == "__main__":
    unittest.main()
