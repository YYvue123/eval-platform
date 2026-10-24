"""Persist observable specialist inputs, tool calls and outputs, never private reasoning."""
from datetime import datetime

from app.models import AgentRun
from app.utils.jsonutil import dumps, loads


async def record_delegation(db, delegation, event_type, payload=None):
    from app.services.redaction import redact_secrets
    from app.services.agent_runtime import append_event

    records = loads(delegation.evidence_json, [])
    event = {"seq": len(records) + 1, "type": event_type, "at": datetime.utcnow().isoformat() + "Z",
             **redact_secrets(payload or {})}
    records.append(event)
    delegation.evidence_json = dumps(records)
    if delegation.run_id:
        run = await db.get(AgentRun, delegation.run_id)
        if run:
            await append_event(db, run, f"subagent.{event_type}", {"delegation_id": delegation.id,
                               "role": delegation.role, **event}, step_id=f"delegation-{delegation.id}")
    await db.flush()
