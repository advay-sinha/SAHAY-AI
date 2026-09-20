"""Deterministic text pipeline: detectors, extraction, recommendations, SVI.

Standard library unittest. All text is fictional.
"""

import unittest

from ml.assessment import assess
from ml.nlp import langid
from ml.nlp.detectors import match_turn, score_dimension
from ml.nlp.extraction import dialogue_slots, extract
from ml.nlp.recommend import recommend


def V(i, text, state="S1"):
    return {"id": f"t{i}", "speaker": "victim", "text": text, "state": state}


class TestMatching(unittest.TestCase):
    def test_hinglish_hindi_and_english_terms_match(self):
        self.assertTrue(match_turn("D6", "gaon mein hukka paani band kar diya"))
        self.assertTrue(match_turn("D6", "गाँव में बहिष्कार हो रहा है"))
        self.assertTrue(match_turn("D6", "there is a social boycott against us"))

    def test_ascii_terms_respect_word_boundaries(self):
        self.assertIsNone(match_turn("D8", "the first time we met"))   # "fir" inside "first"
        self.assertTrue(match_turn("D8", "we filed an FIR last week"))

    def test_negation_cancels_a_threat(self):
        self.assertIsNone(match_turn("D3", "nobody threatened us"))
        self.assertIsNone(match_turn("D3", "unhone koi dhamki nahi di"))
        self.assertIsNone(match_turn("D3", "उन्होंने धमकी नहीं दी"))

    def test_negation_stays_inside_its_clause(self):
        self.assertTrue(match_turn("D3", "they didn't stop, they threatened us again"))

    def test_legal_urgency_is_not_negation_sensitive(self):
        self.assertTrue(match_turn("D8", "police ne FIR nahi likhi"))

    def test_d6_terms_containing_negation_words_still_match(self):
        self.assertTrue(match_turn("D6", "we are not allowed to use the water"))


class TestScoring(unittest.TestCase):
    def test_before_enough_is_heard_a_silent_dimension_is_unscored(self):
        r = score_dimension("D7", [V(1, "hello")])
        self.assertIsNone(r["score"])
        self.assertIsNone(r["confidence"])

    def test_after_listening_a_silent_dimension_is_a_low_confidence_zero(self):
        r = score_dimension("D7", [V(i, "nothing medical here") for i in range(3)])
        self.assertEqual(r["score"], 0.0)
        self.assertEqual(r["basis"], "no_evidence_after_listening")

    def test_corroboration_raises_score_and_confidence(self):
        one = score_dimension("D3", [V(1, "they threatened us")])
        two = score_dimension("D3", [V(1, "they threatened us"), V(2, "dhamki di phir se")])
        self.assertGreater(two["score"], one["score"])
        self.assertGreater(two["confidence"], one["confidence"])
        self.assertEqual(two["evidence_turn_ids"], ["t1", "t2"])

    def test_repeated_future_threat_never_reaches_the_override_threshold(self):
        turns = [V(i, "woh wapas aayenge aur maar denge") for i in range(1, 8)]
        r = score_dimension("D1", turns)
        self.assertLess(r["score"], 70.0)

    def test_imminent_presence_reaches_the_override_threshold(self):
        r = score_dimension("D1", [V(1, "they are outside my house with sticks")])
        self.assertGreaterEqual(r["score"], 70.0)


class TestLangId(unittest.TestCase):
    def test_scripts_and_hinglish(self):
        self.assertEqual(langid.identify("मुझे धमकी दी गई है")["lang"], "hi")
        self.assertEqual(langid.identify("humein gaon mein paani nahi lene dete")["lang"], "hinglish")
        self.assertEqual(langid.identify("they threatened us after the complaint")["lang"], "en")

    def test_unreadable_input_is_low_confidence(self):
        self.assertTrue(langid.aggregate(["??? 123"])["low"])


class TestAssessment(unittest.TestCase):
    RICH = [
        V(1, "Complaint ke baad se gaon mein humara hukka paani band kar diya hai."),
        V(2, "Police ne report nahi likhi. Pradhan ke logon ne dhamki di ki complaint wapas lo."),
        V(3, "Abhi ghar pe hain, par woh bol kar gaye ki wapas aayenge.", "S2"),
    ]

    def test_consent_declined_suppresses_everything(self):
        r = assess(self.RICH, consent_granted=False, channel="mobile_chat")
        self.assertTrue(r["suppressed"])
        self.assertIsNone(r["svi"])
        self.assertIsNone(r["band"])
        self.assertEqual(r["dims"], {})
        self.assertEqual(r["alerts"], [])
        self.assertEqual(r["recommendations"], [])
        self.assertIsNone(r["structured"])

    def test_early_conversation_abstains_with_no_hidden_score(self):
        r = assess(self.RICH[:1], True, channel="mobile_chat")
        self.assertTrue(r["needs_human"])
        self.assertIsNone(r["svi"])
        self.assertIsNone(r["band"])
        self.assertEqual(r["recommendations"], [])
        self.assertTrue(r["cause"].startswith("abstain:"))

    def test_alerts_fire_before_the_score_is_available(self):
        r = assess(self.RICH[:2], True, channel="mobile_chat")
        self.assertIsNone(r["band"])
        self.assertIn("threat", [a["type"] for a in r["alerts"]])
        self.assertIn("coercion", [a["type"] for a in r["alerts"]])

    def test_d4_is_reported_unavailable_not_estimated(self):
        r = assess(self.RICH, True, channel="mobile_chat")
        self.assertIsNone(r["dims"]["D4"]["score"])
        self.assertEqual(r["dims"]["D4"]["basis"], "structurally_unavailable_on_text_channel")
        self.assertIn("unavailable", r["uncertainty"]["acoustic"])

    def test_a_scored_band_carries_its_cause(self):
        r = assess(self.RICH, True, channel="mobile_chat")
        self.assertIsNotNone(r["band"])
        self.assertEqual(r["cause"], "weighted_sum")

    def test_every_score_and_alert_cites_real_turns(self):
        r = assess(self.RICH, True, channel="mobile_chat")
        ids = {t["id"] for t in self.RICH}
        for dim, v in r["dims"].items():
            self.assertTrue(set(v["evidence_turn_ids"]) <= ids, dim)
            if v["score"]:
                self.assertTrue(v["evidence_turn_ids"], f"{dim} scored with no evidence")
        for a in r["alerts"]:
            self.assertTrue(a["evidence_turn_ids"])
            self.assertTrue(set(a["evidence_turn_ids"]) <= ids)

    def test_imminent_danger_forces_critical(self):
        turns = self.RICH[:2] + [V(3, "abhi woh lathi le kar ghar ke bahar khade hain", "S2")]
        r = assess(turns, True, channel="mobile_chat")
        self.assertEqual(r["band"], "Critical")
        self.assertTrue(r["overrides_applied"])
        self.assertTrue(r["cause"].startswith("override:"))
        self.assertIn("emergency", [x["action_type"] for x in r["recommendations"]])

    def test_crisis_language_forces_critical_and_a_crisis_alert(self):
        turns = self.RICH[:2] + [V(3, "I want to die, I cannot go on", "S2")]
        r = assess(turns, True, channel="mobile_chat")
        self.assertEqual(r["band"], "Critical")
        self.assertIn(("crisis", "critical"), [(a["type"], a["severity"]) for a in r["alerts"]])

    def test_conflicting_safety_evidence_abstains(self):
        # "I am safe" plus a (non-imminent) threat: the system cannot tell which
        # is true, so it abstains rather than picking one.
        turns = self.RICH[:2] + [
            V(3, "I am safe now", "S2"),
            V(4, "but they said they will come back and kill us"),
        ]
        r = assess(turns, True, channel="mobile_chat")
        self.assertEqual(extract(turns)["safety_now"]["value"], "conflicting")
        self.assertIn("conflicting_evidence", r["abstention_reasons"])
        self.assertIsNone(r["svi"])
        self.assertIsNone(r["band"])

    def test_imminent_danger_beats_a_conflicting_safe_statement(self):
        # Recall first: "I am safe" does not cancel "they are outside my house".
        # The band is Critical, and the conflict is surfaced for the officer.
        turns = self.RICH[:2] + [
            V(3, "I am safe now", "S2"),
            V(4, "they are outside my house right now"),
        ]
        r = assess(turns, True, channel="mobile_chat")
        self.assertEqual(r["band"], "Critical")
        self.assertTrue(r["uncertainty"]["quality_flags"].get("conflicting_evidence"))

    def test_poor_input_abstains(self):
        r = assess([V(1, "?? ok"), V(2, "hm"), V(3, "..")], True, channel="mobile_chat")
        self.assertTrue(r["needs_human"])
        self.assertIsNone(r["svi"])

    def test_output_is_deterministic(self):
        self.assertEqual(assess(self.RICH, True, channel="mobile_chat"), assess(self.RICH, True, channel="mobile_chat"))

    def test_nothing_is_diagnostic(self):
        r = assess(self.RICH, True, channel="mobile_chat")
        text = str(r).lower()
        for word in ("ptsd", "depress", "disorder", "diagnos", "psychiatric", "patient"):
            self.assertNotIn(word, text)


class TestExtractionAndSlots(unittest.TestCase):
    def test_fields_keep_original_language_and_cite_turns(self):
        turns = [V(1, "पिछले हफ्ते प्रधान ने धमकी दी"), V(2, "chot lagi hai")]
        rec = extract(turns)
        self.assertIn("पिछले हफ्ते", rec["incident"]["value"])
        self.assertEqual(rec["incident"]["source_turn_ids"], ["t1"])
        self.assertEqual(rec["medical_need"]["source_turn_ids"], ["t2"])
        self.assertIn("प्रधान", [p["value"] for p in rec["persons"]])

    def test_s2_is_answered_only_by_a_turn_given_in_s2(self):
        turns = [V(1, "they threatened to come back"), V(2, "more detail here")]
        slots = dialogue_slots(turns, extract(turns))
        self.assertNotEqual(slots["_sources"].get("safety_now"), "answered")
        turns.append(V(3, "abhi ghar pe hoon", "S2"))
        slots = dialogue_slots(turns, extract(turns))
        self.assertEqual(slots["_sources"]["safety_now"], "answered")


class TestRecommendations(unittest.TestCase):
    def test_every_recommendation_awaits_a_decision_and_cites_evidence(self):
        dims = {"D3": {"score": 90, "confidence": 0.8, "evidence_turn_ids": ["t2"]},
                "D8": {"score": 85, "confidence": 0.75, "evidence_turn_ids": ["t1"]}}
        recs = recommend(dims, "Moderate", crisis=False)
        self.assertTrue(recs)
        for r in recs:
            self.assertEqual(r["status"], "awaiting_decision")
            self.assertTrue(r["evidence_turn_ids"])
            self.assertTrue(0 < r["confidence"] <= 1)
        self.assertIn("witness_protection", [r["action_type"] for r in recs])

    def test_nothing_is_recommended_without_evidence(self):
        self.assertEqual(recommend({}, None, crisis=False), [])


if __name__ == "__main__":
    unittest.main()
