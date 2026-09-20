"""Real human identities: the one shape used for authors, reviewers and
adjudicators. Standard library only.

Independence rests entirely on knowing *which human* did each thing, so an
identity here is two fields, not one:

  person_id   the real human. Stable, project-assigned, e.g. ``person-004``.
              Two accounts belonging to the same human share it, which is how
              the assignment tool refuses to hand one person two reviewer
              slots on the same sample.
  identity    the account that signed the record (a GitHub username), so the
              record is traceable to something the project already controls.

A ``kind`` other than ``human`` is refused outright, and so are placeholder,
bot and AI-shaped names. That check is a filter, not a proof: a determined
human can type a plausible name, and no deterministic rule can tell a real
reviewer from a convincing fiction. What it does guarantee is that nothing in
this repository can quietly fill a record with ``TODO-reviewer-1``, an agent
name or a bot account, and that any such record is refused at import rather
than discovered at freeze.
"""

import re
from typing import Any, List, Mapping, Sequence

#: Account name: GitHub's rule, optionally written with a leading "@".
ACCOUNT_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
#: Stable person key: lower-case, digits and dashes, e.g. person-012.
PERSON_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}$")
#: Placeholder, bot and AI-shaped names. Refused for every role.
NON_HUMAN_RE = re.compile(
    r"(^todo)|(^tbd)|(^xxx)|(^n/?a$)|(bot$)|(\[bot\])|claude|anthropic|openai|chatgpt|gpt|copilot|gemini|"
    r"llama|mistral|assistant|(^ai[-_]?)|llm|automated|placeholder|example|dummy|test-?user",
    re.IGNORECASE)

LANGUAGES = ("en", "hi", "hinglish")
PERSON_FIELDS = {"person_id", "identity", "kind", "role", "languages", "code_switch_competent"}


def normal_account(identity: Any) -> str:
    return str(identity or "").lstrip("@").strip()


def validate_person(person: Mapping[str, Any], where: str = "person") -> List[str]:
    """Problems with one identity block. Empty means usable."""
    errs: List[str] = []
    if not isinstance(person, Mapping):
        return [f"{where} must be an object with {sorted(PERSON_FIELDS)}"]
    extra = set(person) - PERSON_FIELDS
    missing = PERSON_FIELDS - set(person)
    if extra:
        errs.append(f"{where}: unknown fields {sorted(extra)}")
    if missing:
        return errs + [f"{where}: missing fields {sorted(missing)}"]

    pid = str(person["person_id"] or "")
    if not PERSON_ID_RE.match(pid):
        errs.append(f"{where}: person_id must look like person-012")
    if NON_HUMAN_RE.search(pid):
        errs.append(f"{where}: placeholder, bot or AI person_id")

    account = normal_account(person["identity"])
    if not ACCOUNT_RE.match(account):
        errs.append(f"{where}: identity must be an account name (GitHub username)")
    if NON_HUMAN_RE.search(account):
        errs.append(f"{where}: placeholder, bot or AI identities cannot author, review or adjudicate")
    if person["kind"] != "human":
        errs.append(f"{where}: kind must be 'human'")
    if len(str(person["role"] or "").strip()) < 4:
        errs.append(f"{where}: role is required and must name a real function")
    if NON_HUMAN_RE.search(str(person["role"] or "")):
        errs.append(f"{where}: role names an AI or placeholder")

    langs = person["languages"]
    if not isinstance(langs, list) or not langs:
        errs.append(f"{where}: languages must be a non-empty list")
    else:
        for lang in langs:
            if lang not in LANGUAGES:
                errs.append(f"{where}: unknown language {lang!r}")
        if len(set(langs)) != len(langs):
            errs.append(f"{where}: duplicate language")
    if not isinstance(person["code_switch_competent"], bool):
        errs.append(f"{where}: code_switch_competent must be a bool")
    return errs


def competent_for(person: Mapping[str, Any], language: str) -> bool:
    """Language competency for one sample language, per the staffing policy.

    en        the person reads English.
    hi        the person reads Hindi.
    hinglish  the person reads Hindi AND English and is marked competent in
              Hindi-English code-switching. Reading both scripts is not the
              same skill as reading a code-switched sentence, so both must be
              declared.
    """
    langs: Sequence[str] = person.get("languages") or []
    if language == "en":
        return "en" in langs
    if language == "hi":
        return "hi" in langs
    if language == "hinglish":
        return "hi" in langs and "en" in langs and bool(person.get("code_switch_competent"))
    return False


def same_person(a: Mapping[str, Any], b: Mapping[str, Any]) -> bool:
    """True when two identity blocks are the same human or the same account."""
    return (str(a.get("person_id")) == str(b.get("person_id"))
            or normal_account(a.get("identity")).casefold() == normal_account(b.get("identity")).casefold())
