"""Build an exportable execution summary from server-owned fields."""
from datetime import datetime, timezone
from time import monotonic
from uuid import uuid4

from .agent_tools import TOOLS


def with_receipt(run, *, scope, rounds, started, engine, run_id=None, resumptions=0):
    steps = []
    for step in run["trace"]:
        name = step["tool"]
        steps.append({"round": step.get("round"), "tool": name if name in TOOLS else "unknown_tool",
                      "status": step["result"]["status"]})
    run["receipt"] = {
        "version": 1,
        "run_id": run_id or str(uuid4()),
        "resumptions": resumptions,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_ms": round((monotonic() - started) * 1000),
        "engine": engine,
        "scope": scope,
        "outcome": run.get("status", "completed"),
        "model_rounds": rounds,
        "steps": steps,
    }
    return run
