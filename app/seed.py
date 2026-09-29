"""One-off: reset the local ledger and bulk-load the seed history into Hindsight.
    HINDSIGHT_URL=... [HINDSIGHT_API_KEY=...] python -m app.seed
"""
from .memory import HindsightMemory, build_memory

m = build_memory()
if not isinstance(m, HindsightMemory):
    raise SystemExit("Set HINDSIGHT_URL (and HINDSIGHT_API_KEY for Cloud) first.")
m.reset()
print("Seeded", len(m.items), "memories into bank", m.bank_id, "errors:", m.errors, m.last_error)
