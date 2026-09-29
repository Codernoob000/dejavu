# Déjà Vu: a change-risk agent that learns from being overruled

Reviews a deploy/config change (ship / review / hold) using your team's history, and keeps learning from
**engineer overrides with reasons**, **near-misses and ruled-out causes**, and **service rewrites that make old lessons stale**.

## Run it
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload        # http://localhost:8000  (works offline on a local ledger)
```
With Hindsight (Cloud promo code MEMHACK99, or self-hosted):
```bash
cp .env.example .env   # fill HINDSIGHT_URL / HINDSIGHT_API_KEY (and GROQ_API_KEY if you want LLM briefings)
export $(grep -v '^#' .env | xargs)
python -m app.seed                   # loads ~35 synthetic memories into your Hindsight bank
uvicorn app.main:app
```
Benchmark: `python -m app.bench` (writes `data/benchmark_results.json`, shown in the UI).

## How Hindsight memory is used
| Event | What we do |
|---|---|
| Incident, near-miss, ruled-out cause, rewrite, note (seed history) | `retain_batch`, tagged `service:` / `pattern:` / `kind:`, `document_id` = memory id, timestamp = event date |
| Engineer override + reason, post-ship incident (live) | `retain` on click, same tagging |
| Reviewing a change | `recall` scoped by service/pattern tags with chunks; results are mapped back to structured records via `document_id` |
| Optional briefing | `reflect` (set `DEJAVU_REFLECT=1`) synthesizes an evidence-grounded summary |
| Bank mission | Tells Hindsight what to prioritize: overrides, near-misses, stale lessons |

Verdict logic (`app/agent.py`) is deterministic and auditable: generic prior, adjusted by recalled memories.
Overrides suppress a repeated objection **unless a newer incident supersedes them**; lessons older than a service rewrite are
down-weighted and badged **stale**. An LLM (Groq) only writes the short briefing and can fail without breaking the demo.

## Demo script (3 min)
1. **Inventory cache TTL**: without memory: SHIP. With memory: HOLD, citing the April oversell incident.
2. **Payments retries on a Friday**: HOLD with three cited incidents/near-misses and a ruled-out cause.
3. **Search index migration**: both say REVIEW. Click **Override with a reason**, review again: SHIP, citing your override.
4. **Ledger migration**: memory flags the incident as **stale** (predates the v2 rewrite). Override it, review again.
5. Scroll to the **Learning curve**: 26 errors without memory vs 9 with.
6. Optional: on step 3's SHIP click **It broke after shipping**, review again: HOLD (incident supersedes override).

## Honest notes
- The learning curve is a **simulation**: an oracle plays the org (overrides when a flag was wrong, incidents when a risk was missed). It shows the mechanism, not real-world accuracy.
- The benchmark runs on the local ledger for determinism. The live app talks to Hindsight when configured; if Hindsight errors, it falls back to the ledger and shows the error count in the status pill.
- The Hindsight integration was written against the documented Python client (signatures checked) but **not run against a live server here**. Run `python -m app.seed` first and watch the status pill.
- Data is synthetic. Swap `app/data.py` SEED for real postmortems to make it yours.
