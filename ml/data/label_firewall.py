"""The source-label firewall. Standard library only; no I/O.

External datasets arrive with labels that were made for somebody else's task:
sentiment, emotion, stress, "suicide" as a subreddit of origin, hate speech.
They look adjacent to SAHAY's safety labels, and that is exactly the danger:
a column called `class = suicide` is a statement about where a Reddit post was
found, not a human judgement that its author was at risk tonight. Letting it
flow into a crisis label, a routing decision or an SVI dimension would publish
a safety number measured against a different question.

So a source label is kept only as *source metadata*, namespaced as
``source:<dataset>:<value>`` so it can never collide with a SAHAY category, and
every route from a source label to a SAHAY target goes through ``map_to_sahay``,
which refuses.

What is refused, and why
------------------------
Hard prohibitions (``FORBIDDEN_EQUIVALENCES``) are refused whatever evidence is
offered, because the two concepts are different things, not uncertain
estimates of the same thing:

  stress                   != crisis / self-harm
  depression label         != a psychiatric diagnosis
  suicide-related label    != immediate-danger ground truth
  negative sentiment       != vulnerability
  emotion intensity        != SVI
  Hindi text emotion       != acoustic distress (D4)
  hate speech              != continuing threat (without contextual human review)
  neutral/positive sentiment != safe or no-alert ground truth

Every other mapping into a SAHAY target needs a separate *human mapping
record*: a named reviewer, written reasoning and provenance. Even a complete,
valid record does not activate a mapping today: ``AUTHORISED_MAPPINGS`` is
empty, because no mapping was approved in ML Task 5, and an approval is a lead
decision recorded in the registry's ``sahay_dimension_mappings`` with an
approved study id — not something this module can grant.
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Tuple

FIREWALL_VERSION = "1.0.0"

#: Every SAHAY target a source label might be pushed into. Refused by default.
SAHAY_TARGETS = (
    # detector categories (ml/eval/schema.py)
    "crisis_self_harm", "immediate_danger", "continuing_threat", "medical_urgency",
    "isolation_boycott_displacement", "legal_urgency", "communication_safety_coercion",
    "explicit_human_request",
    # SVI dimensions and outputs
    "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "svi", "band",
    # routing and escalation
    "routing", "routed_critical", "no_alert", "safe",
    # clinical
    "diagnosis",
)

#: Source-label families. A dataset spec assigns each raw label to one family.
SOURCE_FAMILIES = (
    "stress", "depression", "suicide_related", "sentiment_negative", "sentiment_neutral",
    "sentiment_positive", "sentiment_unspecified", "emotion", "emotion_intensity", "hate_speech",
    "not_hate_speech", "non_suicide", "other",
)

#: (source family, SAHAY target) pairs refused whatever evidence is offered.
FORBIDDEN_EQUIVALENCES: Dict[Tuple[str, str], str] = {
    ("stress", "crisis_self_harm"): "stress is not crisis or self-harm",
    ("depression", "diagnosis"): "a depression label is not a psychiatric diagnosis",
    ("suicide_related", "immediate_danger"): "a suicide-related source label is not immediate-danger ground truth",
    ("suicide_related", "crisis_self_harm"): "a subreddit-of-origin label is not a human crisis judgement",
    ("suicide_related", "routed_critical"): "a subreddit-of-origin label is not a routing decision",
    ("sentiment_negative", "svi"): "negative sentiment is not vulnerability",
    ("sentiment_negative", "band"): "negative sentiment is not an SVI band",
    ("emotion_intensity", "svi"): "emotion intensity is not the SVI",
    ("emotion_intensity", "band"): "emotion intensity is not an SVI band",
    ("emotion", "D4"): "text emotion is not acoustic distress",
    ("emotion_intensity", "D4"): "text emotion intensity is not acoustic distress",
    ("hate_speech", "continuing_threat"): "hate speech is not continuing threat without contextual human review",
    ("sentiment_neutral", "safe"): "neutral sentiment is not safe ground truth",
    ("sentiment_neutral", "no_alert"): "neutral sentiment is not no-alert ground truth",
    ("sentiment_positive", "safe"): "positive sentiment is not safe ground truth",
    ("sentiment_positive", "no_alert"): "positive sentiment is not no-alert ground truth",
    ("non_suicide", "safe"): "a non-suicide subreddit label is not safe ground truth",
    ("non_suicide", "no_alert"): "a non-suicide subreddit label is not no-alert ground truth",
    ("not_hate_speech", "safe"): "absence of hate speech is not safety",
    ("sentiment_unspecified", "svi"): "a sentiment class of unpublished polarity is not vulnerability",
    ("sentiment_unspecified", "band"): "a sentiment class of unpublished polarity is not an SVI band",
    ("sentiment_unspecified", "safe"): "a sentiment class is not safe ground truth",
    ("sentiment_unspecified", "no_alert"): "a sentiment class is not no-alert ground truth",
}

#: Targets no text source may ever populate, whatever the family.
NEVER_FROM_TEXT = {
    "D4": "D4 is acoustic distress; a text source has no acoustic channel",
    "diagnosis": "SAHAY never diagnoses",
    "svi": "the SVI is computed by the deterministic engine, never copied from a source label",
    "band": "a band is an SVI output, never copied from a source label",
}

#: Mappings approved by the leads. Empty: no mapping was authorised in ML Task 5.
AUTHORISED_MAPPINGS: Tuple[str, ...] = ()

MAPPING_ATTESTATION = ("I reviewed this mapping myself, I am not an automated system, and I understand that it "
                       "does not take effect until the leads approve it.")
MAPPING_FIELDS = {"mapping_id", "dataset_id", "source_category", "source_family", "sahay_target", "reviewer",
                  "reviewer_role", "reasoning", "provenance", "timestamp", "attestation"}
_ID = re.compile(r"^MAP-[A-Z0-9-]{3,40}$")
_ACCOUNT = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_NON_HUMAN = re.compile(r"(^todo)|(bot$)|(\[bot\])|claude|anthropic|openai|chatgpt|gpt|copilot|gemini|"
                        r"assistant|(^ai[-_]?)|llm|automated|placeholder", re.IGNORECASE)
MIN_REASONING = 40


class LabelFirewallError(Exception):
    """A source label was about to become a SAHAY label, band, SVI or D4 value."""


def source_category(dataset_id: str, raw_label: Any) -> str:
    """The namespaced form a raw label is stored as. Never a SAHAY category."""
    value = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(raw_label).strip())[:60] or "_empty"
    return f"source:{dataset_id}:{value}"


def is_sahay_category(name: str) -> bool:
    return str(name) in SAHAY_TARGETS


def validate_mapping_record(record: Mapping[str, Any]) -> List[str]:
    """Problems with a human mapping record. Empty means the record is well formed.

    Well formed is not approved: see ``map_to_sahay``.
    """
    if not isinstance(record, Mapping):
        return ["mapping record must be an object"]
    errs: List[str] = []
    missing = MAPPING_FIELDS - set(record)
    extra = set(record) - MAPPING_FIELDS
    if missing:
        return [f"missing fields {sorted(missing)}"]
    if extra:
        errs.append(f"unknown fields {sorted(extra)}")
    if not _ID.match(str(record["mapping_id"])):
        errs.append("mapping_id must look like MAP-EXT-001")
    if record["sahay_target"] not in SAHAY_TARGETS:
        errs.append(f"sahay_target must be one of {SAHAY_TARGETS}")
    if record["source_family"] not in SOURCE_FAMILIES:
        errs.append(f"source_family must be one of {SOURCE_FAMILIES}")
    if not str(record["source_category"]).startswith("source:"):
        errs.append("source_category must be a namespaced source:<dataset>:<value>")
    reviewer = str(record["reviewer"]).lstrip("@")
    if not _ACCOUNT.match(reviewer) or _NON_HUMAN.search(reviewer):
        errs.append("reviewer must be a real human account; placeholder, bot and AI identities are refused")
    if len(str(record["reviewer_role"]).strip()) < 4:
        errs.append("reviewer_role is required")
    if len(str(record["reasoning"]).strip()) < MIN_REASONING:
        errs.append(f"reasoning of at least {MIN_REASONING} characters is required")
    if not str(record["provenance"]).strip():
        errs.append("provenance is required")
    if record["attestation"] != MAPPING_ATTESTATION:
        errs.append("the mapping attestation is missing or altered")
    try:
        if datetime.fromisoformat(str(record["timestamp"])).tzinfo is None:
            errs.append("timestamp needs a timezone")
    except ValueError:
        errs.append("timestamp must be ISO 8601")
    return errs


def map_to_sahay(source_family: str, sahay_target: str,
                 mapping_record: Optional[Mapping[str, Any]] = None) -> None:
    """Refuse to turn a source label into a SAHAY target. Always raises today.

    The refusal reason is specific, so a caller learns *why*: a hard
    prohibition, a target no text may populate, a missing or malformed human
    record, or — for a well-formed record — the absence of a lead approval.
    """
    if sahay_target not in SAHAY_TARGETS:
        raise LabelFirewallError(f"{sahay_target!r} is not a SAHAY target; nothing to map")
    forbidden = FORBIDDEN_EQUIVALENCES.get((source_family, sahay_target))
    if forbidden:
        raise LabelFirewallError(f"forbidden equivalence: {forbidden}")
    if sahay_target in NEVER_FROM_TEXT:
        raise LabelFirewallError(f"never from a source label: {NEVER_FROM_TEXT[sahay_target]}")
    if mapping_record is None:
        raise LabelFirewallError("automatic mapping is not authorised: a separate human mapping record is required")
    problems = validate_mapping_record(mapping_record)
    if problems:
        raise LabelFirewallError("the human mapping record is invalid: " + "; ".join(problems))
    if mapping_record["source_family"] != source_family or mapping_record["sahay_target"] != sahay_target:
        raise LabelFirewallError("the mapping record is for a different source family or target")
    if mapping_record["mapping_id"] not in AUTHORISED_MAPPINGS:
        raise LabelFirewallError("no mapping is authorised: the record is well formed but has not been approved "
                                 "by the leads and registered with an approved study id")
    raise LabelFirewallError("mapping application is not implemented in this release")  # pragma: no cover


def refusals() -> Dict[str, str]:
    """Every hard refusal, for reports and documentation."""
    out = {f"{family} -> {target}": why for (family, target), why in sorted(FORBIDDEN_EQUIVALENCES.items())}
    out.update({f"* -> {target}": why for target, why in sorted(NEVER_FROM_TEXT.items())})
    return out
