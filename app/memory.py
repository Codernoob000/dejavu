"""Memory layer.

Ledger        - in-process structured store (also the offline/fallback backend, and what the benchmark uses).
HindsightMemory - every event is ALSO retained in Hindsight (tagged by service/pattern/kind, document_id = memory id);
                  recall goes through Hindsight's 4-way retrieval and results are mapped back via document_id.
                  If Hindsight is unreachable the app degrades to the ledger and reports it in /api/status.
"""
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from datetime import date, datetime

from .data import SEED

HEADER_RE = re.compile(r"\[(m\d+)\] (\w+) \| ([\w\-\*]+) \| ([\w\-\*]+) \| (\d{4}-\d{2}-\d{2}) \| (.*)", re.S)


def today_iso():
    # never earlier than the synthetic history's "present", so live overrides sort after seed events
    return max(date.today(), date(2026, 9, 29)).isoformat()


@dataclass
class Mem:
    id: str
    kind: str      # INCIDENT | NEARMISS | DEADEND | OVERRIDE | REWRITE | NOTE
    service: str
    pattern: str
    date: str
    text: str

    def header(self):
        return f"[{self.id}] {self.kind} | {self.service} | {self.pattern} | {self.date} | {self.text}"

    def to_dict(self):
        return asdict(self)


class Ledger:
    def __init__(self, path=None, seed=True):
        self.items: list[Mem] = []
        self.path = path
        if path and os.path.exists(path):
            self.items = [Mem(**d) for d in json.load(open(path))]
        elif seed:
            for k, s, p, d, t in SEED:
                self._add(k, s, p, d, t)
            self._save()

    # -- core
    def _add(self, kind, service, pattern, d, text):
        m = Mem(f"m{len(self.items) + 1:03d}", kind, service, pattern, d, text)
        self.items.append(m)
        return m

    def _save(self):
        if self.path:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            json.dump([m.to_dict() for m in self.items], open(self.path, "w"), indent=1)

    def retain(self, kind, service, pattern, text, d=None):
        m = self._add(kind, service, pattern, d or today_iso(), text)
        self._save()
        return m

    def recall(self, query, service, pattern, limit=14):
        def rank(m):
            return (m.service == service and (m.pattern in (pattern, "*"))) * 4 + (m.pattern == pattern) * 2 + (m.service == service)
        hits = [m for m in self.items if rank(m) > 0]
        return sorted(hits, key=lambda m: (-rank(m), m.date))[:limit]

    def all(self):
        return list(self.items)

    def reset(self):
        self.items = []
        for k, s, p, d, t in SEED:
            self._add(k, s, p, d, t)
        self._save()


class HindsightMemory(Ledger):
    def __init__(self, base_url, api_key=None, bank_id="dejavu-demo", path=None):
        super().__init__(path=path)
        from hindsight_client import Hindsight
        self.bank_id = bank_id
        self.client = Hindsight(base_url=base_url, api_key=api_key, timeout=30.0)
        self.errors = 0
        self.last_error = None
        self.retained = 0
        # The sync Hindsight client drives an asyncio loop internally; FastAPI runs handlers on many threads.
        # Funnel every call through ONE worker thread so the loop is never touched from two threads.
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._ensure_bank()

    MISSION = ("I review production change requests for a platform team. I remember incidents, near-misses, ruled-out "
               "causes, service rewrites and, most importantly, engineer overrides with their reasons, so I can "
               "stop repeating objections that were already answered and warn about risks that already bit us.")

    def _call(self, fn, **kw):
        """Run a client call on the dedicated thread; retry once on transient failure."""
        last = None
        for attempt in range(2):
            try:
                return self._pool.submit(lambda: fn(**kw)).result(timeout=60)
            except Exception as e:
                last = e
                time.sleep(0.3)
        raise last

    def _ensure_bank(self):
        try:
            self._call(self.client.create_bank,bank_id=self.bank_id, name="Deja Vu", mission=self.MISSION)
        except Exception as e:  # bank may already exist
            self.last_error = f"create_bank: {e}"

    def _tags(self, m):
        return [f"service:{m.service}", f"pattern:{m.pattern}", f"kind:{m.kind.lower()}"]

    def _retain_hs(self, m, asynchronous=True):
        try:
            self._call(
                self.client.retain,
                bank_id=self.bank_id, content=m.header(),
                context=f"{m.kind} for {m.service} ({m.pattern})",
                timestamp=datetime.fromisoformat(m.date), document_id=m.id,
                tags=self._tags(m), retain_async=asynchronous)
            self.retained += 1
        except Exception as e:
            self.errors += 1
            self.last_error = f"retain: {e}"

    def retain(self, kind, service, pattern, text, d=None):
        m = super().retain(kind, service, pattern, text, d)
        self._retain_hs(m)
        return m

    def seed_hindsight(self):
        """Bulk-load the seed history into Hindsight (run once via `python -m app.seed`)."""
        items = [{"content": m.header(), "context": f"{m.kind} for {m.service} ({m.pattern})",
                  "timestamp": datetime.fromisoformat(m.date), "document_id": m.id, "tags": self._tags(m)}
                 for m in self.items]
        self._call(self.client.retain_batch, bank_id=self.bank_id, items=items, retain_async=False)
        self.retained += len(items)

    def recall(self, query, service, pattern, limit=14):
        # DEJAVU_STRICT=1: rely ONLY on Hindsight recall (use this to prove Hindsight is doing the work)
        strict = bool(os.getenv("DEJAVU_STRICT"))
        found = {} if strict else {m.id: m for m in super().recall(query, service, pattern, limit)}
        try:
            r = self._call(
                self.client.recall,
                bank_id=self.bank_id, query=query, budget="mid", max_tokens=2048, include_chunks=True,
                tags=[f"service:{service}", f"pattern:{pattern}"], tags_match="any")
            by_id = {m.id: m for m in self.items}
            for res in r.results:
                mid = getattr(res, "document_id", None)
                if mid in by_id:
                    found.setdefault(mid, by_id[mid])
                    continue
                chunk = (r.chunks or {}).get(getattr(res, "chunk_id", None))
                hit = HEADER_RE.search(chunk.text if chunk else res.text)
                if hit and hit.group(1) in by_id:
                    found.setdefault(hit.group(1), by_id[hit.group(1)])
        except Exception as e:
            self.errors += 1
            self.last_error = f"recall: {e}"
        return list(found.values())[:limit + 6]

    def brief(self, service, pattern):
        """Hindsight reflect: a synthesized, evidence-grounded briefing for this change type."""
        try:
            a = self._call(
                self.client.reflect,
                bank_id=self.bank_id, budget="low",
                query=f"What should I know before changing {pattern} on {service}? Include past incidents, "
                      f"ruled-out causes, and any engineer overrides and whether they are still valid.")
            return a.text
        except Exception as e:
            self.errors += 1
            self.last_error = f"reflect: {e}"
            return None

    def reset(self):
        super().reset()
        self.bank_id = f"{self.bank_id.split('-r')[0]}-r{int(time.time())}"
        self._ensure_bank()
        self.seed_hindsight()

    def status(self):
        return {"backend": "hindsight", "bank": self.bank_id, "retained": self.retained,
                "errors": self.errors, "last_error": self.last_error}


def build_memory():
    path = os.path.join(os.path.dirname(__file__), "..", "data", "ledger.json")
    url = os.getenv("HINDSIGHT_URL")
    if url:
        try:
            return HindsightMemory(url, os.getenv("HINDSIGHT_API_KEY"), os.getenv("HINDSIGHT_BANK", "dejavu-demo"), path)
        except Exception as e:
            print("Hindsight unavailable, using local ledger:", e)
    return Ledger(path)


def status_of(mem):
    return mem.status() if hasattr(mem, "status") else {"backend": "local-ledger", "retained": len(mem.items), "errors": 0}