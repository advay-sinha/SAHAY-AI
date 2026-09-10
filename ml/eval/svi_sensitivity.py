"""SVI sensitivity analysis. Reads the frozen engine; changes nothing.

Standard library only, deterministic. Every number here is computed by
`ml.svi.compute` (and, for the future-threat ceiling, by the text detectors).
Findings that look like problems are written up separately as PROPOSALS in
ml/eval/PROPOSALS.md; weights and thresholds are never edited here.

The four kinds of "missing or low" evidence are kept apart:
  structurally_unavailable  no measurement path on the channel (D4 on text):
                            weight removed, SVI renormalised (PC-08)
  missing_by_failure        should have been measured but was not (D4 on a
                            voice channel with no acoustic model): abstain,
                            never renormalised
  low_confidence            measured, but not trusted: counts toward the
                            aggregate confidence floor, abstains below it
  measured_low              measured and genuinely low (score 0, confident):
                            contributes zero with its full weight
"""

from typing import Any, Dict, List

from ..nlp.detectors import score_dimension
from ..svi import compute
from ..svi.dimensions import BANDS, DIMENSION_ORDER, SCORING_VERSION, WEIGHTS, band_for
from ..svi.overrides import CONFIDENCE_FLOOR, CRITICAL_OVERRIDE_MIN_CONFIDENCE, CRITICAL_OVERRIDE_THRESHOLD

TEXT = {"structurally_unavailable": ["D4"]}
NOT_D4 = [d for d in DIMENSION_ORDER if d != "D4"]
SAFE_CONF = 0.55  # below the override minimum, above the abstention floor


def _uniform(value: float, conf: float = 0.9, dims=NOT_D4, **over):
    scores = {d: value for d in dims}
    scores.update(over)
    confs = {d: conf for d in scores}
    return scores, confs


def weights_table() -> List[Dict[str, Any]]:
    rows = []
    base_s, base_c = _uniform(50.0)
    base_c.update(D1=SAFE_CONF, D2=SAFE_CONF)
    base = compute(base_s, base_c, TEXT)["svi"]
    for d in DIMENSION_ORDER:
        row = {"dimension": d, "weight": WEIGHTS[d]}
        if d == "D4":
            row.update(text_effective_weight=0.0, text_delta_per_10_points=None,
                       note="structurally unavailable on text; 0.12 of the weight mass is redistributed")
        else:
            s = dict(base_s, **{d: 60.0})
            delta = round(compute(s, base_c, TEXT)["svi"] - base, 4)
            row.update(text_effective_weight=round(WEIGHTS[d] / 0.88, 6), text_delta_per_10_points=delta)
        rows.append(row)
    return rows


def band_boundaries() -> List[Dict[str, Any]]:
    rows = []
    for low, name in sorted(BANDS):
        if low == 0:
            continue
        for v in (round(low - 0.01, 2), low, round(low + 0.01, 2)):
            s, c = _uniform(v)
            c.update(D1=SAFE_CONF, D2=SAFE_CONF)
            r = compute(s, c, TEXT)
            rows.append({"input": v, "svi": r["svi"], "band": r["band"], "boundary": name})
    return rows


def rounding() -> Dict[str, Any]:
    """The SVI is rounded to 2 dp BEFORE the band is applied, so a raw value a
    hair under a boundary can land on it. Measured, not assumed."""
    out = []
    for raw in (29.994, 29.995, 29.996, 54.994, 54.995, 74.994, 74.995):
        s, c = _uniform(raw)
        c.update(D1=SAFE_CONF, D2=SAFE_CONF)
        r = compute(s, c, TEXT)
        out.append({"raw_uniform_score": raw, "svi": r["svi"], "band": r["band"],
                    "band_of_unrounded": band_for(raw)})
    changed = [o for o in out if o["band"] != o["band_of_unrounded"]]
    return {"rows": out, "band_changed_by_rounding": changed}


def overrides() -> List[Dict[str, Any]]:
    rows = []
    for dim in ("D1", "D2"):
        for score in (CRITICAL_OVERRIDE_THRESHOLD - 0.01, CRITICAL_OVERRIDE_THRESHOLD):
            for conf in (CRITICAL_OVERRIDE_MIN_CONFIDENCE - 0.01, CRITICAL_OVERRIDE_MIN_CONFIDENCE):
                s, c = _uniform(10.0)
                s[dim], c[dim] = score, conf
                r = compute(s, c, TEXT)
                rows.append({"dimension": dim, "score": score, "confidence": round(conf, 2),
                             "band": r["band"], "overrides": r["overrides_applied"]})
    for flag in ("crisis_interrupt_fired", "immediate_danger_confirmed"):
        s, c = _uniform(5.0)
        r = compute(s, c, {**TEXT, flag: True})
        rows.append({"flag": flag, "uniform_score": 5.0, "band": r["band"], "svi": r["svi"],
                     "overrides": r["overrides_applied"]})
    return rows


def evidence_kinds() -> List[Dict[str, Any]]:
    s, c = _uniform(60.0)
    c.update(D1=SAFE_CONF, D2=SAFE_CONF)
    cases = [
        ("structurally_unavailable (D4 on text)", s, c, TEXT),
        ("missing_by_failure (D4 on voice, no acoustics)", s, c, {"acoustic_not_measured": True}),
        ("missing, no declaration (D4 absent, weight kept)", s, c, {}),
        ("low_confidence (all measured at conf 0.30)", s, {d: 0.30 for d in s}, TEXT),
        ("measured_low (D4 measured 0 at conf 0.9)", dict(s, D4=0.0), dict(c, D4=0.9), {}),
    ]
    rows = []
    for label, sc, cf, q in cases:
        r = compute(sc, cf, q)
        rows.append({"case": label, "svi": r["svi"], "band": r["band"], "needs_human": r["needs_human"],
                     "weight_denominator": r["weight_denominator"],
                     "aggregate_confidence": r["aggregate_confidence"],
                     "abstention_reasons": r["abstention_reasons"]})
    return rows


def abstention_floor() -> List[Dict[str, Any]]:
    rows = []
    for conf in (round(CONFIDENCE_FLOOR - 0.001, 3), CONFIDENCE_FLOOR, round(CONFIDENCE_FLOOR + 0.001, 3)):
        s, c = _uniform(50.0, conf)
        r = compute(s, c, TEXT)
        rows.append({"uniform_confidence": conf, "aggregate_confidence": r["aggregate_confidence"],
                     "band": r["band"], "abstention_reasons": r["abstention_reasons"]})
    return rows


def future_threat_ceiling() -> List[Dict[str, Any]]:
    """Repeated FUTURE threats (D1 tier 2) must stay below the override."""
    rows = []
    for n in (1, 2, 3, 5, 8):
        turns = [{"id": f"t{i}", "text": "They said they will come back and kill us."} for i in range(1, n + 1)]
        d1 = score_dimension("D1", turns)
        rows.append({"repeated_turns": n, "d1_score": d1["score"], "d1_confidence": d1["confidence"],
                     "reaches_override": (d1["score"] or 0) >= CRITICAL_OVERRIDE_THRESHOLD})
    return rows


def weak_combinations() -> List[Dict[str, Any]]:
    rows = []
    # D2 is binary in the text pipeline (0 or 100), so it is never "weak".
    for label, k, score in (("3 weak dims at 45, rest 0", 3, 45.0), ("5 weak dims at 45, rest 0", 5, 45.0),
                            ("all 7 lexicon dims at 45 (tier 1)", 7, 45.0),
                            ("all 7 lexicon dims at 64 (tier-1 ceiling)", 7, 64.0)):
        dims = ["D3", "D5", "D6", "D7", "D8", "D9", "D1"][:k]
        s = {d: (score if d in dims else 0.0) for d in NOT_D4}
        c = {d: (SAFE_CONF if d in ("D1", "D2") else 0.9) for d in NOT_D4}
        r = compute(s, c, TEXT)
        rows.append({"case": label, "svi": r["svi"], "band": r["band"]})
    return rows


def ceilings() -> Dict[str, Any]:
    """Highest SVI reachable on text WITHOUT a hard override.

    D2 is binary in the text pipeline (0 or 100) and 100 always forces
    Critical, so without a crisis D2 contributes 0. D1 below the override
    tops out at the tier-2 ceiling (69).
    """
    s = {d: 100.0 for d in NOT_D4}
    s["D2"], s["D1"] = 0.0, 69.0
    c = {d: 0.9 for d in NOT_D4}
    r = compute(s, c, TEXT)
    return {"max_non_override_text_svi": r["svi"], "band": r["band"],
            "normalization_factor": r["normalization_factor"], "weight_denominator": r["weight_denominator"]}


def determinism(repeats: int = 50) -> Dict[str, Any]:
    s, c = _uniform(47.3, D1=12.0, D8=88.0)
    first = compute(s, c, TEXT)
    same = all(compute(s, c, TEXT) == first for _ in range(repeats))
    contrib = round(sum(b["contribution"] for b in first["breakdown"] if b["contribution"] is not None), 2)
    return {"repeats": repeats, "identical": same, "svi": first["svi"], "sum_of_contributions": contrib,
            "explanation_matches_svi": abs(contrib - first["svi"]) <= 0.05}


def run() -> Dict[str, Any]:
    result = {
        "scoring_version": SCORING_VERSION,
        "weights": weights_table(),
        "band_boundaries": band_boundaries(),
        "rounding": rounding(),
        "hard_overrides": overrides(),
        "evidence_kinds": evidence_kinds(),
        "abstention_floor": abstention_floor(),
        "future_threat_ceiling": future_threat_ceiling(),
        "weak_combinations": weak_combinations(),
        "ceilings": ceilings(),
        "determinism": determinism(),
    }
    result["findings"] = findings(result)
    return result


def findings(r: Dict[str, Any]) -> List[str]:
    out = []
    changed = r["rounding"]["band_changed_by_rounding"]
    if changed:
        out.append(f"Rounding: the band is applied to the SVI after rounding to 2 dp, so {len(changed)} of "
                   f"{len(r['rounding']['rows'])} probed raw values within 0.005 below a boundary take the "
                   "higher band. Consistent with what the console displays; recorded, not changed.")
    ceiling = r["ceilings"]["max_non_override_text_svi"]
    out.append(f"Ceiling: without a hard override the highest text SVI is {ceiling} "
               f"({r['ceilings']['band']}). D2 is binary in the text pipeline and a D2 of 100 always forces "
               "Critical, so D2's 0.18 weight never moves a band on its own. See PROPOSALS.md P-SVI-1.")
    top = r["weak_combinations"][-1]
    out.append(f"Weak indicators: seven tier-1 lexicon signals at their ceiling reach {top['svi']} ({top['band']}) "
               "with no strong indicator. Intended or not is a lead decision; recorded, not changed.")
    if all(not row["reaches_override"] for row in r["future_threat_ceiling"]):
        out.append("Future-threat ceiling holds: repeated future threats stay at or below 69, under the "
                   "override threshold of 70.")
    return out
