"""EXT-129 (project owner, 2026-09-26): datasets open for MVP model training and validation.

What changed: review status and record-level prohibitions no longer gate research, training or
validation, and a source label may act as a weak-supervision training label.
What did not: diagnosis, the SVI, the band, routing and text-derived D4 are never learned from
a source label; the official label path (map_to_sahay) is unchanged; nothing opens the product,
the demo, victim-facing output or the official locked set to dataset content.
"""

import unittest

from ml.data import external_corpus as xc
from ml.data import governance as gov
from ml.data import label_firewall as fw


class TestMapForTraining(unittest.TestCase):
    def test_a_source_label_may_train_a_detector_with_its_caveat(self):
        m = fw.map_for_training("reddit_suicide_detection", "suicide_related", "crisis_self_harm", "training")
        self.assertEqual(m["evidence_class"], fw.WEAK_SUPERVISION)
        self.assertEqual(m["basis"], "EXT-129")
        self.assertEqual(m["caveat"], fw.FORBIDDEN_EQUIVALENCES[("suicide_related", "crisis_self_harm")])
        self.assertIsNone(fw.map_for_training("x", "other", "legal_urgency", "validation")["caveat"])

    def test_invariant_targets_stay_refused_even_for_training(self):
        for target in ("diagnosis", "svi", "band", "D4", "routing", "routed_critical"):
            with self.assertRaises(fw.LabelFirewallError, msg=target):
                fw.map_for_training("x", "depression", target, "training")

    def test_only_training_and_validation(self):
        for purpose in ("product", "official_evaluation", "locked_test", "demo"):
            with self.assertRaises(fw.LabelFirewallError, msg=purpose):
                fw.map_for_training("x", "stress", "crisis_self_harm", purpose)
        for bad_family, bad_target in (("not_a_family", "crisis_self_harm"), ("stress", "not_a_target")):
            with self.assertRaises(fw.LabelFirewallError):
                fw.map_for_training("x", bad_family, bad_target, "training")

    def test_the_official_label_path_is_unchanged(self):
        with self.assertRaises(fw.LabelFirewallError):
            fw.map_to_sahay("suicide_related", "crisis_self_harm")
        self.assertEqual(fw.AUTHORISED_MAPPINGS, ())


class TestProductStaysClosed(unittest.TestCase):
    def test_product_and_official_purposes_remain_refused(self):
        for purpose in ("mvp_product", "product", "demo", "victim_facing_output", "backend_ingestion",
                        "locked_test", "blind_corpus_intake", "official_evaluation", "redistribution",
                        "external_upload"):
            self.assertIn(purpose, xc.OVERRIDE_REFUSED_PURPOSES)

    def test_no_dataset_becomes_the_official_locked_set(self):
        reg = gov.load_registry()
        for rec in reg["datasets"]:
            with self.assertRaises(gov.GovernanceError, msg=rec["id"]):
                gov.assert_can_be_locked_test(reg, rec["id"])


if __name__ == "__main__":
    unittest.main()
