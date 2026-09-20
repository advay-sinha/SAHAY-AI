"""Documented exit codes for the blind-corpus commands. Standard library only.

One code per refusal *class*, so a script can branch on the reason without
parsing text. No code, message or log line built from these ever carries
scenario narrative: the caller gets an id, a count and a reason class.
"""

from typing import Dict

EXIT_OK = 0                        #: the command did what was asked
EXIT_INTERNAL = 1                  #: unexpected error (reserved for the interpreter)
EXIT_USAGE = 2                     #: invalid command, argument or configuration (unset/bad root)
EXIT_SCHEMA = 3                    #: a submission, record or roster failed schema validation
EXIT_PRIVACY = 4                   #: possible personal information; human inspection required
EXIT_CONTAMINATION = 5             #: overlap with an exposed corpus; human adjudication required
EXIT_MISSING_REVIEW = 6            #: a required human review is absent
EXIT_CONFLICT = 7                  #: reviewers disagree
EXIT_ADJUDICATION = 8              #: adjudication is required or invalid
EXIT_COVERAGE = 9                  #: the coverage plan is not satisfied
EXIT_LEDGER = 10                   #: a ledger, hash chain or content hash failed to verify
EXIT_FREEZE_REFUSED = 11           #: freeze preconditions are not met
EXIT_NO_FROZEN_CORPUS = 12         #: evaluation asked for, no frozen corpus exists
EXIT_EVALUATION_FAILED = 13        #: the evaluation run itself failed
EXIT_STATE = 14                    #: an invalid or skipped status transition
EXIT_FIREWALL = 15                 #: a prediction module was loaded before freeze

#: code -> short, narrative-free description. Printed by `blind_corpus exit-codes`.
DESCRIPTIONS: Dict[int, str] = {
    EXIT_OK: "success",
    EXIT_INTERNAL: "internal error",
    EXIT_USAGE: "invalid command or configuration",
    EXIT_SCHEMA: "schema validation failure",
    EXIT_PRIVACY: "privacy / possible personal information review required",
    EXIT_CONTAMINATION: "contamination or similarity review required",
    EXIT_MISSING_REVIEW: "missing required human review",
    EXIT_CONFLICT: "reviewer conflict",
    EXIT_ADJUDICATION: "adjudication required or invalid",
    EXIT_COVERAGE: "coverage plan incomplete",
    EXIT_LEDGER: "ledger or hash verification failure",
    EXIT_FREEZE_REFUSED: "freeze refused",
    EXIT_NO_FROZEN_CORPUS: "no frozen corpus",
    EXIT_EVALUATION_FAILED: "evaluation failure",
    EXIT_STATE: "invalid status transition",
    EXIT_FIREWALL: "prediction module loaded before freeze",
}

#: Every code is distinct and every code is described.
assert len(set(DESCRIPTIONS)) == len(DESCRIPTIONS) == 16
