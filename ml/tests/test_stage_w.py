"""Stage W (plan M14, EXT-129): weak-corpus mapping, per-epoch mixing, masks, selection and evaluation helpers.

No Torch and no private data: everything here runs on small in-memory fixtures.
"""

import unittest
from pathlib import Path

from ml.data import governance as gov
from ml.data import label_firewall as fw
from ml.data import weak_corpus as wc
from ml.eval.schema import DETECTOR_CATEGORIES
from ml.training import stage_w as sw
from ml.training import stage_w_eval as swe

ML = Path(__file__).resolve().parents[1]


def seg(uid, dataset, label, split="train", window=0, family=None, opaque=False):
    return {"uid": uid, "family": family or f"F:{uid}", "dataset_id": dataset, "language": "en", "script": "latin",
            "text": "fictional window", "source_labels": [label] if label else [], "aux_split": split,
            "window": window, "weight": 1.0, "opaque_labels": opaque}


class TestWeakCorpus(unittest.TestCase):
    def setUp(self):
        self.maps = wc.mappings(gov.load_registry())

    def test_every_mapping_goes_through_the_firewall_and_carries_a_caveat(self):
        self.assertEqual(len(self.maps), 6)
        for raw, m in self.maps.items():
            self.assertEqual(m["evidence_class"], fw.WEAK_SUPERVISION, raw)
            self.assertTrue(m["caveat"], raw)
            self.assertNotIn(m["target"], fw.NEVER_EVEN_FOR_TRAINING, raw)
        self.assertEqual({m["target"] for m in self.maps.values()}, set(sw.TARGET_HEAD))

    def test_one_dataset_per_target(self):
        per_target = {}
        for m in self.maps.values():
            per_target.setdefault(m["target"], set()).add(m["dataset_id"])
        self.assertTrue(all(len(v) == 1 for v in per_target.values()), per_target)

    def test_forbidden_targets_stay_refused(self):
        for target in ("D4", "svi", "band", "routing", "routed_critical", "diagnosis"):
            with self.assertRaises(fw.LabelFirewallError):
                fw.map_for_training("dreaddit", "stress", target, "training")

    def test_selection_rules(self):
        segs = [seg("r1#w0", "reddit_suicide_detection", "source:reddit_suicide_detection:suicide"),
                seg("r1#w1", "reddit_suicide_detection", "source:reddit_suicide_detection:suicide", window=1,
                    family="F:r1#w0"),
                seg("d1#w0", "dreaddit", "source:dreaddit:1", split="test"),
                seg("h1#w0", "hinglish_hate_speech_local_derivative", None),              # unlabelled: skipped
                seg("e1#w0", "emoinhindi", "source:emoinhindi:fear"),                    # not a Stage W source
                seg("s1#w0", "hinglish_sentiment_kaggle", "source:x:1", opaque=True)]
        rows = wc.select_rows(segs, self.maps)
        self.assertEqual([(r["uid"], r["target"], r["value"], r["split"]) for r in rows],
                         [("d1#w0", "D5", 1, "test"), ("r1#w0", "crisis_self_harm", 1, "train")])

    def test_caps_are_deterministic(self):
        segs = [seg(f"r{i}#w0", "reddit_suicide_detection", "source:reddit_suicide_detection:non-suicide")
                for i in range(20)]
        old = wc.SOURCES["reddit_suicide_detection"]["caps"]["train"]
        wc.SOURCES["reddit_suicide_detection"]["caps"]["train"] = 5
        try:
            a = wc.select_rows(segs, self.maps)
            b = wc.select_rows(list(reversed(segs)), self.maps)
        finally:
            wc.SOURCES["reddit_suicide_detection"]["caps"]["train"] = old
        self.assertEqual(len(a), 5)
        self.assertEqual([r["uid"] for r in a], [r["uid"] for r in b])

    def test_a_family_crossing_buckets_is_refused(self):
        segs = [seg("d1#w0", "dreaddit", "source:dreaddit:1", family="F:x"),
                seg("d2#w0", "dreaddit", "source:dreaddit:0", split="test", family="F:x")]
        with self.assertRaises(wc.WeakCorpusError):
            wc.select_rows(segs, self.maps)

    def _zip(self, tmp, train_csv, test_csv):
        import hashlib
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("dreaddit/dreaddit-train.csv", train_csv)
            zf.writestr("dreaddit/dreaddit-test.csv", test_csv)
        data = buf.getvalue()
        path = Path(tmp) / "corpus" / "text" / "english" / "dreaddit" / "dreaddit.zip"
        path.parent.mkdir(parents=True)
        path.write_bytes(data)
        return {"datasets": [{"id": "dreaddit", "local_relative_path": "corpus/text/english/dreaddit/dreaddit.zip",
                              "byte_size": len(data), "sha256": hashlib.sha256(data).hexdigest()}]}

    def test_official_archive_is_parsed_redacted_and_post_disjoint(self):
        import tempfile
        header = "subreddit,post_id,sentence_range,text,id,label\n"
        train = header + ("ptsd,p1,\"[0, 5]\",I cannot stop shaking mail a.b@example.com,1,1\n"
                          "ptsd,p2,\"[0, 5]\",A calm fictional day at work,2,0\n"
                          "ptsd,p9,\"[0, 5]\",Unlabelled fictional row,3,\n")
        test = header + "ptsd,p2,\"[5, 9]\",Same post later in the story,4,1\n"
        with tempfile.TemporaryDirectory() as tmp:
            reg = self._zip(tmp, train, test)
            out = wc.official_dreaddit(Path(tmp), reg, self.maps)
        by_split = {s: [r for r in out["rows"] if r["split"] == s] for s in ("train", "test")}
        self.assertEqual([r["value"] for r in by_split["train"]], [1])        # p2 dropped: its post is in test
        self.assertEqual(out["train_windows_dropped_for_post_overlap"], 1)
        self.assertEqual(out["skipped"], {"train": 1, "test": 0})
        self.assertIn("[EMAIL]", by_split["train"][0]["text"])
        self.assertTrue(all(r["target"] == "D5" and r["evidence_class"] == fw.WEAK_SUPERVISION for r in out["rows"]))

    def test_absent_or_mismatched_archive(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            reg = self._zip(tmp, "text,label\n", "text,label\n")
            self.assertIsNone(wc.official_dreaddit(None, reg, self.maps))
            self.assertIsNone(wc.official_dreaddit(Path(tmp) / "elsewhere", reg, self.maps))
            reg["datasets"][0]["sha256"] = "0" * 64
            with self.assertRaises(wc.WeakCorpusError):
                wc.official_dreaddit(Path(tmp), reg, self.maps)

    def test_csv_without_text_and_label_is_refused(self):
        with self.assertRaises(wc.WeakCorpusError):
            wc.parse_dreaddit_csv(b"body,score\nx,1\n", "train", self.maps)

    def test_builder_never_uses_the_official_mapping(self):
        self.assertNotIn("map_to_sahay", (ML / "data" / "weak_corpus.py").read_text(encoding="utf-8"))


class TestMixing(unittest.TestCase):
    def test_quotas_share_equally_and_pass_on_the_remainder(self):
        self.assertEqual(sw.quotas({"D5": 860, "crisis_self_harm": 20000}, 7492),
                         {"D5": 860, "crisis_self_harm": 6632})
        self.assertEqual(sw.quotas({"D5": 860, "continuing_threat": 15300, "crisis_self_harm": 20000}, 7492),
                         {"D5": 860, "continuing_threat": 3316, "crisis_self_harm": 3316})
        self.assertEqual(sw.quotas({"a": 10}, 4), {"a": 4})

    def test_draw_is_deterministic_and_cycles_through_the_pool(self):
        pools = {"a": [{"id": f"a{i}"} for i in range(10)], "b": [{"id": f"b{i}"} for i in range(3)]}
        e1 = sw.weak_draw(pools, 8, 13, 1)
        self.assertEqual([r["id"] for r in e1], [r["id"] for r in sw.weak_draw(pools, 8, 13, 1)])
        self.assertEqual(sum(r["id"].startswith("b") for r in e1), 3)
        seen = {r["id"] for e in (1, 2) for r in sw.weak_draw(pools, 8, 13, e) if r["id"].startswith("a")}
        self.assertEqual(len(seen), 10)  # two epochs of quota 5 cover all ten windows

    def test_weak_rows_supervise_exactly_one_logit(self):
        for target, head in sw.TARGET_HEAD.items():
            r = sw.weak_row({"uid": "u", "text": "t", "language": "en", "target": target, "value": 1})
            self.assertEqual(sum(r["m"]), 1.0)
            self.assertEqual(r["m"][sw.LABELS.index(head)], 1.0)
            self.assertEqual(r["y"][sw.LABELS.index(head)], 1.0)
            self.assertEqual(r["source"], target)

    def test_arms_use_only_known_targets(self):
        self.assertEqual(sw.ARMS["W0"], ())
        self.assertTrue(set(sw.ARMS["W1"]) < set(sw.ARMS["W2"]))
        for targets in sw.ARMS.values():
            self.assertTrue(set(targets) <= set(sw.TARGET_HEAD))

    def test_fictional_rows_mask_the_d5_logit(self):
        labels = {c: c == "legal_urgency" for c in DETECTOR_CATEGORIES}
        rec = {"id": "F1", "turns": [{"speaker": "victim", "text": "fictional"}], "labels": labels, "language": "en",
               "family": "f", "contrast_group": "g", "negative_labels": [], "challenge_slices": []}
        (row,) = sw.fictional_rows([rec])
        self.assertEqual(row["m"], [1.0] * 8 + [0.0])
        self.assertEqual(row["y"][sw.LABELS.index("legal_urgency")], 1.0)

    def test_label_space(self):
        self.assertEqual(sw.LABELS, tuple(DETECTOR_CATEGORIES) + ("d5_text_distress",))
        for banned in ("D4", "svi", "band", "routing", "diagnosis"):
            self.assertNotIn(banned, sw.LABELS)


class TestPlanAndSelection(unittest.TestCase):
    def test_plan_hash_tracks_the_weak_corpus(self):
        a = sw.plan_hash(sw.plan({"train.jsonl": "1", "test.jsonl": "2"}))
        self.assertEqual(a, sw.plan_hash(sw.plan({"test.jsonl": "2", "train.jsonl": "1"})))
        self.assertNotEqual(a, sw.plan_hash(sw.plan({"train.jsonl": "X", "test.jsonl": "2"})))

    def test_selection_order(self):
        def r(arm, seed, f1, rec, loss):
            return {"arm": arm, "seed": seed, "validation": {"macro": {"f1": f1}, "min_label_recall": rec},
                    "validation_loss": loss}
        runs = [r("W2", 13, 0.70, 0.5, 0.2), r("W1", 13, 0.72, 0.4, 0.3), r("W0", 13, 0.72, 0.4, 0.3),
                r("W0", 42, 0.72, 0.6, 0.9)]
        ranked = sorted(runs, key=sw.selection_key)
        self.assertEqual([(x["arm"], x["seed"]) for x in ranked], [("W0", 42), ("W0", 13), ("W1", 13), ("W2", 13)])

    def test_training_code_never_reads_evaluation_sets(self):
        text = (ML / "training" / "stage_w.py").read_text(encoding="utf-8")
        for name in ("dev.json", "candidates.json", "redteam", "locked.json", "blind_corpus"):
            self.assertNotIn(name, text)
        self.assertNotIn('load_split(root, "synthetic_hardening_holdout")', text)
        self.assertNotIn('load_weak(root, "test")', text)


class TestEvaluationHelpers(unittest.TestCase):
    def test_auroc(self):
        self.assertEqual(swe.auroc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]), 1.0)
        self.assertEqual(swe.auroc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]), 0.0)
        self.assertEqual(swe.auroc([0, 1, 0, 1], [0.5, 0.5, 0.5, 0.5]), 0.5)
        self.assertIsNone(swe.auroc([1, 1], [0.2, 0.3]))

    def test_rules_signal_per_target(self):
        self.assertTrue(swe.rules_fire("crisis_self_harm", "I want to kill myself."))
        self.assertFalse(swe.rules_fire("crisis_self_harm", "I went to the market."))
        self.assertTrue(swe.rules_fire("continuing_threat", "They threatened us again."))
        self.assertTrue(swe.rules_fire("D5", "I can't sleep since that night."))
        self.assertEqual(set(swe.WEAK_HEAD), set(sw.TARGET_HEAD))
        with self.assertRaises(ValueError):
            swe.rules_fire("D4", "x")

    def test_compare_exposed_lists_ids_not_text(self):
        gold = {c: c == "legal_urgency" for c in DETECTOR_CATEGORIES}
        samples = [{"id": "DEV-X", "gold": gold, "text": "fictional"}]
        model = [{c: c in ("legal_urgency", "medical_urgency") for c in DETECTOR_CATEGORIES}]
        rules = [{c: False for c in DETECTOR_CATEGORIES}]
        out = swe.compare_exposed(samples, model, rules)
        self.assertEqual(out["caught_by_model_only"], ["DEV-X:legal_urgency"])
        self.assertEqual(out["model_false_positives"], ["DEV-X:medical_urgency"])
        self.assertNotIn("fictional", str(out))

    def test_probes_are_labelled_and_balanced(self):
        self.assertEqual({lang for _, lang, _, _ in swe.PROBES}, {"en", "hi", "hinglish"})
        self.assertTrue(any(not ind for _, _, ind, _ in swe.PROBES))
        self.assertIn("locked.json", swe.FORBIDDEN)


if __name__ == "__main__":
    unittest.main()


class TestLogisticBaseline(unittest.TestCase):
    def setUp(self):
        from ml.training import baseline_lr as lr
        self.lr = lr

    def test_features_are_deterministic_and_include_char_trigrams(self):
        f = self.lr.feature_strings("They threatend us")
        self.assertIn("w:threatend", f)
        self.assertIn("b:they_threatend", f)
        self.assertIn("c:<th", f)
        self.assertEqual(self.lr.vectorise("They threatend us"), self.lr.vectorise("they THREATEND us"))
        self.assertEqual(self.lr.vectorise(""), ([], 0.0))

    def test_masked_heads_are_never_updated(self):
        rows = []
        for i in range(40):
            y = [0.0] * len(sw.LABELS)
            m = [0.0] * len(sw.LABELS)
            m[0] = 1.0
            y[0] = float(i % 2)
            rows.append({"id": f"r{i}", "text": "alpha danger" if i % 2 else "beta calm", "y": y, "m": m})
        model, info = self.lr.train(rows, {}, "W0", epochs=5, log=lambda *_: None)
        p_pos, p_neg = model.predict([{"text": "alpha danger"}, {"text": "beta calm"}])
        self.assertGreater(p_pos[0], 0.5)
        self.assertLess(p_neg[0], 0.5)
        self.assertTrue(all(b == 0.0 for b in model.b[1:]))
        self.assertTrue(all(not any(w) for w in model.w[1:]))
        self.assertEqual(info["pos_weights"][sw.LABELS[0]], 1.0)

    def test_top_features_come_only_from_the_given_vocabulary(self):
        model = self.lr.LogReg(len(sw.LABELS))
        for f in ("w:secret", "w:visible"):
            model.w[0][self.lr.bucket(f)] = 1.0
        top = self.lr.top_features(model, {"w:visible"})
        listed = [x for item in top[sw.LABELS[0]] for x in item["features"]]
        self.assertEqual(listed, ["w:visible"])

    def test_arms_mirror_stage_w(self):
        self.assertEqual(set(self.lr.ARMS.values()) <= set(sw.ARMS), True)
        self.assertEqual(self.lr.HYPER["threshold"], 0.5)
