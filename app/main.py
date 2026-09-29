import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import bench
from .agent import _stale, assess, llm_summary
from .data import PATTERN_RISK, SCENARIOS, SERVICES
from .memory import build_memory, status_of

ROOT = os.path.join(os.path.dirname(__file__), "..")
app = FastAPI(title="Déjà Vu: change-risk agent that learns from overrides")
memory = build_memory()


class Change(BaseModel):
    service: str
    pattern: str
    day: str = "Tue"
    description: str = ""


class Override(BaseModel):
    service: str
    pattern: str
    reason: str


class Incident(BaseModel):
    service: str
    pattern: str
    summary: str


def _check(service, pattern):
    if service not in SERVICES or pattern not in PATTERN_RISK:
        raise HTTPException(422, "Unknown service or change type")


@app.get("/api/meta")
def meta():
    return {"services": SERVICES, "patterns": list(PATTERN_RISK), "scenarios": SCENARIOS}


@app.get("/api/status")
def status():
    return status_of(memory)


@app.post("/api/assess")
def do_assess(c: Change):
    _check(c.service, c.pattern)
    ch = c.model_dump()
    without, with_mem = assess(ch, None), assess(ch, memory)
    if hasattr(memory, "brief"):
        with_mem["hindsight_brief"] = memory.brief(c.service, c.pattern) if os.getenv("DEJAVU_REFLECT") else None
    for r in (with_mem,):
        text = llm_summary(ch, r)
        if text:
            r["summary"] = text
    return {"stateless": without, "memory": with_mem}


@app.post("/api/override")
def override(o: Override):
    _check(o.service, o.pattern)
    if len(o.reason.strip()) < 8:
        raise HTTPException(422, "Give a reason (at least a short sentence) so the lesson is reusable.")
    m = memory.retain("OVERRIDE", o.service, o.pattern, o.reason.strip())
    return {"saved": m.to_dict()}


@app.post("/api/incident")
def incident(i: Incident):
    _check(i.service, i.pattern)
    m = memory.retain("INCIDENT", i.service, i.pattern, i.summary.strip() or "Incident after shipping this change.")
    return {"saved": m.to_dict()}


@app.get("/api/memories")
def memories(service: str, pattern: str = ""):
    items = [m for m in memory.all() if m.service == service and (not pattern or m.pattern in (pattern, "*"))]
    return sorted((dict(m.to_dict(), stale=_stale(m, service)) for m in items), key=lambda m: m["date"], reverse=True)


@app.post("/api/reset")
def reset():
    memory.reset()
    return {"ok": True, **status_of(memory)}


@app.get("/api/benchmark")
def benchmark():
    if not os.path.exists(bench.OUT):
        os.makedirs(os.path.dirname(bench.OUT), exist_ok=True)
        json.dump(bench.run(), open(bench.OUT, "w"), indent=1)
    return json.load(open(bench.OUT))


@app.post("/api/benchmark/run")
def benchmark_run():
    res = bench.run()
    json.dump(res, open(bench.OUT, "w"), indent=1)
    return res


@app.get("/")
def index():
    return FileResponse(os.path.join(ROOT, "static", "index.html"))


app.mount("/static", StaticFiles(directory=os.path.join(ROOT, "static")), name="static")
