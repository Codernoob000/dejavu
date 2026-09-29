"""Change-risk agent.

The verdict is deterministic and auditable: a generic risk prior, adjusted by recalled memories
(incidents, near-misses, ruled-out causes, overrides, rewrites). An LLM (Groq) then writes a short
plain-English briefing; if it fails or no key is set, a template is used, so the demo never breaks.
"""
import os
import time

import httpx

from .data import PATTERN_RISK, REWRITES

HOLD_AT, REVIEW_AT = 0.60, 0.40
_llm_cache: dict = {}


def generic_score(pattern, day):
    return PATTERN_RISK.get(pattern, 0.3) + (0.15 if day == "Fri" else 0.0)


def _verdict(score):
    score = round(score, 2)
    return "HOLD" if score >= HOLD_AT else "REVIEW" if score >= REVIEW_AT else "SHIP"


def _key(m):
    """Order by date, then by the order memories were retained (same-day events)."""
    return (m.date, int(m.id[1:]))


def _stale(m, service):
    rw = REWRITES.get(service)
    return bool(rw) and m.date < rw and m.kind != "REWRITE"


def assess(change, memory=None):
    service, pattern, day = change["service"], change["pattern"], change.get("day", "Tue")
    g = generic_score(pattern, day)
    score, reasons, cited, related, conf = g, [], [], [], 0.55

    if g >= REVIEW_AT:
        reasons.append({"kind": "generic", "text": f"{pattern} changes are riskier than average."})
    if day == "Fri":
        reasons.append({"kind": "generic", "text": "Friday deploy: less time to react before the weekend."})

    if memory is not None:
        query = f"{pattern} change on {service}: {change.get('description', '')}"
        mems = memory.recall(query, service, pattern)
        exact = [m for m in mems if m.service == service and m.pattern in (pattern, "*")]
        rw = REWRITES.get(service)

        def pick(kind, stale):
            return sorted([m for m in exact if m.kind == kind and _stale(m, service) == stale], key=_key)

        fresh_inc, stale_inc = pick("INCIDENT", False), pick("INCIDENT", True)
        fresh_nm, stale_nm = pick("NEARMISS", False), pick("NEARMISS", True)
        deadends = sorted([m for m in exact if m.kind == "DEADEND"], key=_key)
        overrides = sorted([m for m in exact if m.kind == "OVERRIDE" and (not rw or m.date >= rw)], key=_key)

        if fresh_inc:
            score += 0.5 + (0.2 if len(fresh_inc) > 1 else 0)
            conf += 0.1 * min(len(fresh_inc), 3)
            for m in fresh_inc[-3:]:
                reasons.append({"kind": "incident", "memory_id": m.id, "text": f"Same change caused an incident on {m.date}: {m.text}"})
                cited.append(m)
        if fresh_nm:
            score += 0.2
            conf += 0.05
            for m in fresh_nm[-2:]:
                reasons.append({"kind": "nearmiss", "memory_id": m.id, "text": f"Near-miss on {m.date}: {m.text}"})
                cited.append(m)
        for m in stale_inc + stale_nm:
            conf -= 0.15
            reasons.append({"kind": "stale", "memory_id": m.id,
                            "text": f"Lesson from {m.date} predates the {service} rewrite ({rw}); weight reduced. Was: {m.text}"})
            cited.append(m)
        for m in deadends[-2:]:
            reasons.append({"kind": "deadend", "memory_id": m.id, "text": f"Already ruled out: {m.text}"})
            cited.append(m)

        if overrides:
            o = overrides[-1]
            newer_inc = [m for m in fresh_inc if _key(m) > _key(o)]
            if newer_inc:
                reasons.append({"kind": "superseded", "memory_id": o.id,
                                "text": f"Override from {o.date} is superseded by the incident on {newer_inc[-1].date}."})
            else:
                score = min(score, 0.20)
                conf += 0.25
                reasons.append({"kind": "override", "memory_id": o.id,
                                "text": f"Engineers overrode this objection on {o.date}: {o.text}"})
            cited.append(o)

        seen = {m.id for m in cited}
        for m in mems:
            if m.kind == "INCIDENT" and m.pattern == pattern and m.service != service and len(related) < 2:
                related.append(m)
            if m.kind == "NOTE" and m.service == service and m.pattern == pattern and m.id not in seen:
                cited.append(m)
                reasons.append({"kind": "note", "memory_id": m.id, "text": f"Context: {m.text}"})

    if not reasons:
        reasons.append({"kind": "generic", "text": "No risk signals for this change type."})
    verdict = _verdict(score)
    result = {
        "verdict": verdict, "score": round(score, 2), "generic_score": round(g, 2),
        "confidence": round(max(0.3, min(0.95, conf)), 2), "memory_used": memory is not None,
        "reasons": reasons,
        "cited": [dict(m.to_dict(), stale=_stale(m, service)) for m in cited],
        "related": [m.to_dict() for m in related],
    }
    result["summary"] = template_summary(change, result)
    return result


def template_summary(change, r):
    lead = {"HOLD": "Hold this change.", "REVIEW": "Get a second look before shipping.", "SHIP": "Looks safe to ship."}[r["verdict"]]
    kinds = {x["kind"] for x in r["reasons"]}
    why = ("An earlier engineer override still applies." if "override" in kinds else
           "This has burned the team before." if "incident" in kinds else
           "The only history here predates a rewrite, so treat it with caution." if "stale" in kinds else
           "Nothing in history changes the generic picture.")
    return f"{lead} {why}"


# ------------------------------------------------------------------ LLM briefing (optional, fault tolerant)
MODELS = ["openai/gpt-oss-120b", "qwen/qwen3-32b"]


def llm_summary(change, result):
    key = os.getenv("GROQ_API_KEY")
    if not key:
        return None
    ck = (change["service"], change["pattern"], change.get("day"), result["verdict"], tuple(r["text"] for r in result["reasons"]))
    if ck in _llm_cache:
        return _llm_cache[ck]
    facts = "\n".join(f"- {r['text']}" for r in result["reasons"])
    prompt = (f"A change is proposed: {change.get('description')} (service {change['service']}, {change.get('day')}).\n"
              f"Verdict already decided: {result['verdict']}.\nEvidence:\n{facts}\n\n"
              "Write 2 sentences for the on-call engineer explaining the verdict. Use only the evidence above; "
              "mention dates when given. No preamble.")
    for model in MODELS:
        for attempt in range(2):
            try:
                r = httpx.post("https://api.groq.com/openai/v1/chat/completions", timeout=12,
                               headers={"Authorization": f"Bearer {key}"},
                               json={"model": model, "temperature": 0.2, "max_tokens": 200,
                                     "messages": [{"role": "user", "content": prompt}]})
                r.raise_for_status()
                text = (r.json()["choices"][0]["message"]["content"] or "").strip()
                if text:
                    _llm_cache[ck] = text
                    return text
            except Exception:
                time.sleep(0.4 * (attempt + 1))
    return None
