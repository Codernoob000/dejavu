"""Replay 46 synthetic changes through a stateless agent and the memory agent.

An oracle plays the engineering org: when an agent flags a change that is actually safe, a human overrides it
with a reason; when an agent ships a change that is actually risky, an incident happens and is retained.
Only the memory agent retains these events. Errors: false alarm = flagged but safe, miss = SHIP but risky.

    python -m app.bench                # local ledger (deterministic, no keys)
"""
import json
import os

from .agent import assess
from .data import INCIDENT_TEXT, OVERRIDE_REASONS, build_stream, truth_risky
from .memory import Ledger

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "benchmark_results.json")


def _err(verdict, risky):
    flagged = verdict != "SHIP"
    return "miss" if (risky and not flagged) else "false_alarm" if (flagged and not risky) else None


def run(memory=None):
    mem = memory or Ledger(path=None)
    stream, rows = build_stream(), []
    cum = {"stateless": 0, "memory": 0}
    for ch in stream:
        combo, risky = (ch["service"], ch["pattern"]), truth_risky((ch["service"], ch["pattern"]), ch["i"])
        a, b = assess(ch, None), assess(ch, mem)
        ea, eb = _err(a["verdict"], risky), _err(b["verdict"], risky)
        cum["stateless"] += bool(ea)
        cum["memory"] += bool(eb)
        event = None
        if eb == "false_alarm" and combo in OVERRIDE_REASONS:
            mem.retain("OVERRIDE", *combo, OVERRIDE_REASONS[combo], d=ch["date"])
            event = "override"
        elif eb == "miss" and combo in INCIDENT_TEXT:
            mem.retain("INCIDENT", *combo, INCIDENT_TEXT[combo], d=ch["date"])
            event = "incident"
        rows.append({"i": ch["i"], "date": ch["date"], "service": ch["service"], "pattern": ch["pattern"],
                     "risky": risky, "stateless": {"verdict": a["verdict"], "error": ea},
                     "memory": {"verdict": b["verdict"], "error": eb, "event": event, "cited": len(b["cited"])},
                     "cum_stateless": cum["stateless"], "cum_memory": cum["memory"]})
    n = len(rows)
    half = n // 2
    rate = lambda key, sl: round(sum(1 for r in rows[sl] if r[key]["error"]) / max(1, len(rows[sl])), 3)
    summary = {
        "changes": n, "stateless_errors": cum["stateless"], "memory_errors": cum["memory"],
        "reduction_pct": round(100 * (1 - cum["memory"] / max(1, cum["stateless"]))),
        "stateless_first_half_rate": rate("stateless", slice(0, half)), "stateless_second_half_rate": rate("stateless", slice(half, n)),
        "memory_first_half_rate": rate("memory", slice(0, half)), "memory_second_half_rate": rate("memory", slice(half, n)),
        "overrides_learned": sum(1 for r in rows if r["memory"]["event"] == "override"),
        "incidents_learned": sum(1 for r in rows if r["memory"]["event"] == "incident"),
        "note": "Simulated org: oracle-provided overrides/incidents. Stateless agent uses the same generic prior with no memory.",
    }
    return {"summary": summary, "rows": rows}


if __name__ == "__main__":
    res = run()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=1)
    print(json.dumps(res["summary"], indent=1))
