"""External-dataset governance tests. Standard library only; fully offline.

These tests never touch the real local archives: every ZIP is a small
fictional file created in a temporary directory, and SAHAY_DATASETS_ROOT is
never required.
"""

import copy
import json
import os
import re
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from ml.data import archive_safety as az
from ml.data import audit_external
from ml.data import governance as gov
from ml.eval import checks
from ml.eval.evaluate import evaluate
from ml.tests.source_scan import iter_source_files

ML = Path(__file__).resolve().parents[1]
REPO = ML.parent
REG = gov.load_registry()


def record(**over):
    base = copy.deepcopy(gov.get(REG, "emoinhindi"))
    base.update(over)
    return base


def make_zip(path: Path, members, compress=zipfile.ZIP_DEFLATED):
    with zipfile.ZipFile(path, "w", compress) as z:
        for name, data in members:
            z.writestr(name, data)
    return path


class TestRegistry(unittest.TestCase):
    def test_committed_registry_is_valid(self):
        self.assertEqual(gov.validate_registry(REG), [])

    def test_schema_document_matches_the_validator(self):
        schema = json.loads((ML / "data" / "registry" / "schema.json").read_text(encoding="utf-8"))
        item = schema["properties"]["datasets"]["items"]
        self.assertEqual(sorted(item["properties"]), sorted(gov.REQUIRED_FIELDS))
        self.assertEqual(item["properties"]["review_status"]["enum"], list(gov.REVIEW_STATES))
        self.assertEqual(item["properties"]["modality"]["enum"], list(gov.MODALITIES))

    def test_required_review_states_exist(self):
        for state in ("unregistered", "metadata_pending", "licence_pending", "quarantined", "integrity_verified",
                      "approved_for_research", "approved_for_evaluation", "approved_for_training", "rejected"):
            self.assertIn(state, gov.REVIEW_STATES)

    def test_downloaded_datasets_are_not_approved(self):
        for rec in REG["datasets"]:
            if rec["download_status"] == "downloaded":
                self.assertFalse(rec["review_status"].startswith("approved_"), rec["id"])
            self.assertFalse(rec["official_locked_test_allowed"], rec["id"])
            self.assertEqual(rec["sahay_dimension_mappings"], {}, rec["id"])

    def test_emoinhindi_is_registered_as_text_at_the_text_path(self):
        rec = gov.get(REG, "emoinhindi")
        self.assertEqual(rec["modality"], "text")
        self.assertTrue(rec["local_relative_path"].startswith("corpus/text/hindi/"))
        self.assertIn("d4_acoustic_distress", rec["prohibited_uses"])

    def test_proposal_entries_are_not_downloaded_and_invent_no_licence(self):
        for rid in ("common_voice_hi", "ravdess_audio_speech", "crema_d", "iemocap", "daic_woz"):
            rec = gov.get(REG, rid)
            self.assertEqual(rec["download_status"], "not_downloaded")
            self.assertEqual(rec["licence_name"], "unknown")
            self.assertIsNone(rec["sha256"])

    def test_all_language_and_modality_combinations_are_supported(self):
        for modality, lang in (("text", "en"), ("text", "hi"), ("text", "hi-Latn"), ("audio", "en"),
                               ("audio", "hi"), ("audio", "mul-IN")):
            self.assertEqual(gov.validate_record(record(modality=modality, primary_language=lang)), [], (modality, lang))

    def test_approval_requires_resolved_licence(self):
        errs = gov.validate_record(record(review_status="approved_for_research", approved_uses=["research"]))
        self.assertTrue(any("unresolved licence" in e for e in errs))

    def test_missing_licence_terms_keep_the_dataset_licence_pending(self):
        for state in gov.REVIEW_STATES:
            errs = gov.validate_record(record(review_status=state, approved_uses=["research"]))
            self.assertEqual(any("unresolved licence" in e for e in errs), state not in gov.PRE_LICENCE_STATES, state)
        for rec in REG["datasets"]:
            if any(gov._is_blank(rec[f]) for f in gov.LICENCE_FIELDS):
                self.assertIn(rec["review_status"], ("licence_pending", "metadata_pending"), rec["id"])

    def test_committed_registry_grants_no_use_and_records_evidence(self):
        for rec in REG["datasets"]:
            self.assertEqual(rec["approved_uses"], [], rec["id"])
            self.assertNotEqual(rec["redistribution"], "permitted", rec["id"])
            self.assertRegex(rec["date_checked"], r"^\d{4}-\d{2}-\d{2}$", rec["id"])
            if rec["download_status"] == "downloaded":
                self.assertTrue(rec["evidence_urls"], rec["id"])
                self.assertTrue(all(u.startswith("https://") for u in rec["evidence_urls"]), rec["id"])
                self.assertIn("d4_acoustic_distress", rec["prohibited_uses"], rec["id"])

    def test_malformed_registries_are_reported_not_raised(self):
        for bad in ([], {"schema_version": gov.REGISTRY_SCHEMA_VERSION, "datasets": [1]},
                    {"schema_version": gov.REGISTRY_SCHEMA_VERSION, "datasets": [record(review_status=5)]}):
            self.assertTrue(gov.validate_registry(bad), bad)

    def test_downloaded_record_needs_hash_and_size(self):
        self.assertTrue(gov.validate_record(record(sha256=None)))
        self.assertTrue(gov.validate_record(record(byte_size=0)))

    def test_machine_specific_paths_are_rejected(self):
        for bad in ("D:/SAHAY-AI-Datasets/x.zip", "C:\\Users\\someone\\x.zip", "/home/user/x.zip"):
            self.assertTrue(gov.validate_record(record(local_relative_path=bad)), bad)
        self.assertNotRegex(json.dumps(REG).replace("https://", "").replace("http://", ""), r"[A-Za-z]:[\\/]")

    def test_dimension_mapping_requires_an_approved_study(self):
        errs = gov.validate_record(record(sahay_dimension_mappings={"D4": {"note": "emotion labels exist"}}))
        self.assertTrue(any("approved study" in e for e in errs))


class TestUseGuards(unittest.TestCase):
    def test_unapproved_datasets_cannot_be_selected(self):
        for rid in ("dreaddit", "emoinhindi", "common_voice_hi"):
            for purpose in ("research", "evaluation", "training"):
                with self.assertRaises(gov.GovernanceError, msg=(rid, purpose)):
                    gov.select_for(REG, rid, purpose)

    def test_dreaddit_can_never_be_the_locked_test_set(self):
        with self.assertRaises(gov.GovernanceError):
            gov.assert_can_be_locked_test(REG, "dreaddit")
        approved = copy.deepcopy(REG)
        rec = gov.get(approved, "dreaddit")
        rec.update(review_status="approved_for_evaluation", licence_name="x", licence_url="https://x",
                   redistribution="not_permitted", commercial_use="not_permitted", approved_uses=["evaluation"],
                   prohibited_uses=[])
        with self.assertRaises(gov.GovernanceError):  # still false by default
            gov.assert_can_be_locked_test(approved, "dreaddit")

    def test_emoinhindi_cannot_populate_d4(self):
        with self.assertRaises(gov.GovernanceError):
            gov.assert_can_populate_dimension(REG, "emoinhindi", "D4")

    def test_an_approved_record_is_selectable_only_for_its_purpose(self):
        reg = copy.deepcopy(REG)
        rec = gov.get(reg, "emoinhindi")
        rec.update(review_status="approved_for_research", licence_name="x", licence_url="https://x",
                   redistribution="not_permitted", approved_uses=["research"], prohibited_uses=["training"])
        self.assertEqual(gov.select_for(reg, "emoinhindi", "research")["id"], "emoinhindi")
        with self.assertRaises(gov.GovernanceError):
            gov.select_for(reg, "emoinhindi", "evaluation")


class TestDatasetRoot(unittest.TestCase):
    def test_missing_root_gives_a_clear_non_sensitive_message(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(gov.ROOT_ENV, None)
            with self.assertRaises(gov.DatasetRootError) as ctx:
                gov.dataset_root(None)
        msg = str(ctx.exception)
        self.assertIn(gov.ROOT_ENV, msg)
        self.assertNotRegex(msg, r"[A-Za-z]:[\\/]")
        with mock.patch.dict(os.environ, {gov.ROOT_ENV: ""}):
            self.assertEqual(audit_external.main(["--out", tempfile.mkdtemp()]), audit_external.EXIT_CONFIG)

    def test_paths_are_confined_to_the_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(gov.resolve_under(root, "corpus/a.zip"), (root / "corpus" / "a.zip").resolve())
            for bad in ("../outside.zip", "/etc/passwd", "C:/x.zip", "corpus/../../x", "..\\x"):
                with self.assertRaises(gov.DatasetRootError, msg=bad):
                    gov.resolve_under(root, bad)


class TestArchiveSafety(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_checksums_are_deterministic(self):
        p = self.dir / "a.bin"
        p.write_bytes(b"fictional bytes")
        q = self.dir / "b.bin"
        q.write_bytes(b"fictional bytes")
        self.assertEqual(az.sha256_file(p), az.sha256_file(p))
        self.assertEqual(az.sha256_file(p), az.sha256_file(q))
        q.write_bytes(b"fictional bytes!")
        self.assertNotEqual(az.sha256_file(p), az.sha256_file(q))
        self.assertRegex(az.sha256_file(p), r"^[0-9a-f]{64}$")

    def test_a_clean_archive_passes(self):
        p = make_zip(self.dir / "ok.zip", [("data/train.csv", "id,label\n1,0\n"), ("README.md", "fictional")])
        r = az.inspect_zip(p)
        self.assertTrue(r["safe"], r["findings"])
        self.assertEqual(r["audio_members"], 0)

    def test_traversal_absolute_ads_and_device_members_are_rejected(self):
        for name, finding in (("../evil.txt", "path_traversal"), ("a/../../evil.txt", "path_traversal"),
                              ("/etc/evil", "absolute_path"), ("C:/evil.txt", "absolute_path"),
                              ("file.txt:stream", "alternate_data_stream_or_drive"), ("CON.txt", "device_name")):
            p = make_zip(self.dir / "x.zip", [(name, "x")])
            r = az.inspect_zip(p)
            self.assertFalse(r["safe"], name)
            self.assertTrue(any(f.startswith(finding) for f in r["findings"]), (name, r["findings"]))

    def test_duplicates_nested_archives_executables_and_encryption_are_rejected(self):
        with zipfile.ZipFile(self.dir / "d.zip", "w") as z:
            z.writestr("a.csv", "1")
            with self.assertWarns(UserWarning):
                z.writestr("a.csv", "2")
        self.assertIn("duplicate_member_names:1", az.inspect_zip(self.dir / "d.zip")["findings"])
        r = az.inspect_zip(make_zip(self.dir / "n.zip", [("inner.zip", "PK"), ("run.exe", "MZ")]))
        self.assertTrue(any(f.startswith("nested_archives_unsupported") for f in r["findings"]))
        self.assertTrue(any(f.startswith("executable_looking_member_names") for f in r["findings"]))
        enc = make_zip(self.dir / "e.zip", [("secret.csv", "x")], compress=zipfile.ZIP_STORED)
        raw = bytearray(enc.read_bytes())
        for sig, flag_offset in ((b"PK", 6), (b"PK", 8)):  # local and central headers
            i = raw.find(sig)
            raw[i + flag_offset] |= 0x1  # set the "encrypted" general-purpose bit
        enc.write_bytes(bytes(raw))
        self.assertTrue(any(f.startswith("encrypted_members") for f in az.inspect_zip(self.dir / "e.zip")["findings"]))

    def test_suspicious_compression_ratio_is_rejected(self):
        p = make_zip(self.dir / "bomb.zip", [("zeros.bin", b"\0" * 2_000_000)])
        r = az.inspect_zip(p)
        self.assertIn("suspicious_member_compression_ratio", r["findings"])
        self.assertFalse(r["safe"])

    def test_oversized_declared_extraction_is_rejected(self):
        p = make_zip(self.dir / "big.zip", [("a.csv", "x" * 5000)], compress=zipfile.ZIP_STORED)
        self.assertIn("declared_size_exceeds_ceiling", az.inspect_zip(p, max_total=1000)["findings"])
        with self.assertRaises(az.UnsafeArchive):
            az.safe_extract(p, self.dir / "out", max_total=1000)

    def test_safe_extract_writes_only_inside_an_empty_destination(self):
        p = make_zip(self.dir / "ok.zip", [("d/a.csv", "id\n1\n")])
        out = self.dir / "dest"
        self.assertEqual(az.safe_extract(p, out)["members"], 1)
        self.assertTrue((out / "d" / "a.csv").is_file())
        with self.assertRaises(az.UnsafeArchive):  # not empty any more
            az.safe_extract(p, out)
        with self.assertRaises(az.UnsafeArchive):
            az.safe_extract(make_zip(self.dir / "t.zip", [("../x.csv", "1")]), self.dir / "dest2")
        self.assertFalse((self.dir / "x.csv").exists())


class TestAuditCommand(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "datasets"
        (self.root / "corpus" / "text" / "english" / "fictional").mkdir(parents=True)
        self.zip = make_zip(self.root / "corpus" / "text" / "english" / "fictional" / "fictional.zip",
                            [("SECRET_MEMBER_NAME.csv", "text\nSENSITIVE FICTIONAL NARRATIVE\n")])
        rec = record(id="fictional_ds", local_relative_path="corpus/text/english/fictional/fictional.zip",
                     archive_filename="fictional.zip", byte_size=self.zip.stat().st_size,
                     sha256=az.sha256_file(self.zip))
        self.reg = {"schema_version": gov.REGISTRY_SCHEMA_VERSION, "description": "test", "datasets": [rec]}
        self.reg_path = Path(self.tmp.name) / "registry.json"
        self.out = Path(self.tmp.name) / "out"

    def tearDown(self):
        self.tmp.cleanup()

    def run_audit(self, reg=None, extra=()):
        self.reg_path.write_text(json.dumps(reg or self.reg), encoding="utf-8")
        return audit_external.main(["--root", str(self.root), "--registry", str(self.reg_path),
                                    "--out", str(self.out), *extra])

    def approved(self):
        reg = copy.deepcopy(self.reg)
        reg["datasets"][0].update(review_status="approved_for_research", licence_name="fictional",
                                  licence_url="https://example.invalid/licence", redistribution="not_permitted",
                                  commercial_use="not_permitted", approved_uses=["research"])
        return reg

    def test_pending_governance_has_a_distinct_exit_code(self):
        self.assertEqual(self.run_audit(), audit_external.EXIT_GOVERNANCE)

    def test_integrity_mismatch_fails(self):
        reg = copy.deepcopy(self.reg)
        reg["datasets"][0]["sha256"] = "0" * 64
        self.assertEqual(self.run_audit(reg), audit_external.EXIT_INTEGRITY)
        reg = copy.deepcopy(self.reg)
        reg["datasets"][0]["byte_size"] += 1
        self.assertEqual(self.run_audit(reg), audit_external.EXIT_INTEGRITY)

    def test_unsafe_archive_fails(self):
        make_zip(self.zip, [("../escape.csv", "x")])
        reg = copy.deepcopy(self.reg)
        reg["datasets"][0].update(byte_size=self.zip.stat().st_size, sha256=az.sha256_file(self.zip))
        self.assertEqual(self.run_audit(reg), audit_external.EXIT_INTEGRITY)

    def test_approved_and_verified_passes(self):
        self.assertEqual(self.run_audit(self.approved()), audit_external.EXIT_OK)

    def test_exit_codes_are_distinct(self):
        self.assertEqual(len({audit_external.EXIT_OK, audit_external.EXIT_INTEGRITY, audit_external.EXIT_GOVERNANCE,
                              audit_external.EXIT_CONFIG}), 4)

    def test_invalid_configuration_fails_with_the_config_code(self):
        out = ["--out", str(self.out)]
        missing_root = str(Path(self.tmp.name) / "no-such-root")
        self.reg_path.write_text(json.dumps(self.reg), encoding="utf-8")
        self.assertEqual(audit_external.main(["--root", missing_root, "--registry", str(self.reg_path), *out]),
                         audit_external.EXIT_CONFIG)
        for bad in ("{not json", "[]", json.dumps({"schema_version": gov.REGISTRY_SCHEMA_VERSION, "datasets": [1]})):
            self.reg_path.write_text(bad, encoding="utf-8")
            self.assertEqual(audit_external.main(["--root", str(self.root), "--registry", str(self.reg_path), *out]),
                             audit_external.EXIT_CONFIG, bad)
        absent = str(Path(self.tmp.name) / "absent.json")
        self.assertEqual(audit_external.main(["--root", str(self.root), "--registry", absent, *out]),
                         audit_external.EXIT_CONFIG)
        reg = copy.deepcopy(self.reg)
        reg["datasets"][0]["local_relative_path"] = "../outside.zip"
        self.assertEqual(self.run_audit(reg), audit_external.EXIT_CONFIG)
        self.assertFalse(self.out.exists())  # nothing written on a configuration error

    def test_reports_contain_no_content_names_or_absolute_paths(self):
        self.run_audit()
        for name in ("audit.json", "audit.md"):
            text = (self.out / name).read_text(encoding="utf-8")
            self.assertNotIn("SENSITIVE FICTIONAL NARRATIVE", text)
            self.assertNotIn("SECRET_MEMBER_NAME", text)
            self.assertNotIn(str(self.root), text)
            self.assertNotIn(self.tmp.name, text)

    def test_reports_are_deterministic(self):
        self.run_audit()
        first = (self.out / "audit.json").read_text(encoding="utf-8")
        self.run_audit()
        self.assertEqual(first, (self.out / "audit.json").read_text(encoding="utf-8"))

    def test_registry_is_never_modified(self):
        before = self.reg_path.read_text(encoding="utf-8") if self.reg_path.exists() else None
        self.run_audit()
        self.assertEqual(json.loads(self.reg_path.read_text(encoding="utf-8")), self.reg)
        self.assertTrue(before is None or before == self.reg_path.read_text(encoding="utf-8"))

    def test_extraction_needs_the_explicit_flag_and_approval(self):
        self.run_audit()
        self.assertFalse((self.root / "extracted").exists())
        self.assertEqual(self.run_audit(extra=("--extract", "fictional_ds")), audit_external.EXIT_GOVERNANCE)
        self.assertFalse((self.root / "extracted").exists())
        self.assertEqual(self.run_audit(self.approved(), extra=("--extract", "fictional_ds")), audit_external.EXIT_OK)
        dest = self.root / "extracted" / "fictional_ds" / self.reg["datasets"][0]["sha256"][:12]
        self.assertTrue(dest.is_dir())
        self.assertNotIn(REPO.resolve(), dest.resolve().parents)

    def test_audit_is_offline(self):
        with checks.offline() as net:
            self.run_audit()
        self.assertTrue(net["ok"], net)


class TestExternalDataBoundary(unittest.TestCase):
    def test_no_archive_audio_model_or_dataset_is_tracked(self):
        tracked = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout
        bad_ext = re.compile(r"\.(zip|tar|gz|tgz|7z|rar|wav|mp3|flac|ogg|m4a|opus|pt|bin|safetensors|ckpt|onnx|"
                             r"npy|parquet|arrow)$", re.I)
        offenders = [p for p in tracked.splitlines()
                     if bad_ext.search(p) or p.startswith(("datasets/", "extracted/"))
                     or re.search(r"(^|/)(dreaddit|emoinhindi)[^/]*\.(csv|tsv|json|jsonl|txt)$", p, re.I)]
        self.assertEqual(offenders, [])

    def test_dataset_paths_do_not_appear_in_application_modules(self):
        markers = ("SAHAY_DATASETS_ROOT", "SAHAY-AI-Datasets", "dreaddit", "emoinhindi", "corpus/text/")
        offenders = []
        for path in iter_source_files(ML):
            rel = path.relative_to(ML).as_posix()
            if rel.startswith(("data/", "tests/")) or rel == "eval/checks.py":
                continue
            text = path.read_text(encoding="utf-8")
            offenders += [f"{rel}:{m}" for m in markers if m.casefold() in text.casefold()]
        self.assertEqual(offenders, [])

    def test_eval_corpora_never_reference_external_datasets(self):
        for path in (ML / "eval" / "corpus").glob("*.json"):
            text = path.read_text(encoding="utf-8").casefold()
            for m in ("dreaddit", "emoinhindi", "sahay_datasets_root", "sahay-ai-datasets", ".zip"):
                self.assertNotIn(m, text, (path.name, m))
        for path in (ML / "eval").glob("*.py"):
            self.assertNotRegex(path.read_text(encoding="utf-8"), r"(from|import)\s+(\.\.data|ml\.data)\b", path.name)

    def test_evaluation_needs_no_dataset_root_and_stays_offline(self):
        corpus = json.loads((ML / "eval" / "corpus" / "dev.json").read_text(encoding="utf-8"))
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(gov.ROOT_ENV, None)
            with checks.offline() as net, checks.file_access_log() as opened:
                evaluate(corpus["samples"][:10])
        self.assertTrue(net["ok"])
        self.assertEqual(checks.external_corpus_access(opened), [])


if __name__ == "__main__":
    unittest.main()
