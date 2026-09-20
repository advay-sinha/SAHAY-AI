"""Publish a service's outbound events AFTER its transaction commits.

Publishing never waits on a socket (see app/ws/hub.py), and scheduling an
assessment never waits on the assessment (app/adapters/assessment_runner.py),
so the reply path returns as soon as the database write is durable.
"""

from ..adapters.assessment_runner import runner
from ..ws.hub import hub
from .intake import Outbound


def publish(session_id: str, case_id: str, out: Outbound) -> None:
    for event_type, payload in out.events:
        hub.publish(session_id, event_type, payload)
    if out.schedule_assessment:
        runner.schedule(case_id)
