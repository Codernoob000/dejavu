"""Synthetic-but-realistic data for Déjà Vu: services, seed memories, benchmark world."""
import random
from datetime import date, timedelta

SERVICES = {
    "payments-service": "Card capture and refunds",
    "ledger-api": "Double-entry ledger (v2 rewrite shipped Jun 2026)",
    "auth-gateway": "Login, token refresh, SSO",
    "notification-worker": "Email / SMS / push fan-out",
    "search-indexer": "Catalog search indexing",
    "checkout-web": "Storefront checkout UI",
    "inventory-sync": "Warehouse stock sync",
    "fraud-scorer": "Real-time transaction scoring",
}
# service -> date its lessons before which are considered stale
REWRITES = {"ledger-api": "2026-06-10"}

# Generic (memory-less) risk prior per change pattern, like a linter or a generic LLM would use.
PATTERN_RISK = {
    "retry-config": 0.45, "db-migration": 0.50, "schema-change": 0.45,
    "timeout-change": 0.40, "autoscaling-change": 0.40,
    "feature-flag": 0.15, "cache-ttl": 0.15, "dependency-bump": 0.20,
}

# (kind, service, pattern, date, text)
SEED = [
    ("INCIDENT", "payments-service", "retry-config", "2026-03-12",
     "Raised card-capture retries 3->5. The acquirer throttled us and a retry storm caused 41 min of elevated 5xx (SEV2). Rolled back."),
    ("DEADEND", "payments-service", "retry-config", "2026-03-14",
     "Postmortem ruled out connection-pool exhaustion for the retry-storm incident: pool metrics stayed flat."),
    ("NEARMISS", "payments-service", "retry-config", "2026-05-19",
     "Backoff change caught in canary: p99 latency doubled at 10% traffic. Reverted before full rollout."),
    ("INCIDENT", "payments-service", "retry-config", "2026-06-26",
     "Friday 17:40 retry tweak rolled back after 25 min: duplicate-charge alerts fired for 63 orders."),
    ("INCIDENT", "auth-gateway", "timeout-change", "2026-02-08",
     "Lowered upstream timeout 30s->8s. Token refresh failed for mobile clients on slow networks: 22 min login degradation (SEV2)."),
    ("NEARMISS", "auth-gateway", "timeout-change", "2026-07-02",
     "Timeout change to 12s flagged by synthetic login probes in staging; held back a release."),
    ("INCIDENT", "inventory-sync", "cache-ttl", "2026-04-21",
     "Cache TTL 60s->600s served stale stock counts; 312 SKUs oversold during the flash sale."),
    ("NEARMISS", "inventory-sync", "cache-ttl", "2026-08-05",
     "Proposed TTL 300s caught in review: warehouse feed lag would have exceeded the TTL window."),
    ("INCIDENT", "checkout-web", "feature-flag", "2026-05-03",
     "Flag 'new-address-form' enabled to 100% at once; validation regression blocked EU checkout for 35 min."),
    ("DEADEND", "checkout-web", "feature-flag", "2026-05-05",
     "CDN caching ruled out as cause of the checkout regression; bug was in client-side validation."),
    ("INCIDENT", "ledger-api", "db-migration", "2026-03-04",
     "Long-running ALTER TABLE on ledger_entries locked writes for 14 min (SEV1). Pre-v2 monolith schema."),
    ("REWRITE", "ledger-api", "*", "2026-06-10",
     "ledger-api v2 shipped: online schema migrations, partitioned ledger_entries, new write path."),
    # --- quieter history on other combos (realistic noise the agent must not over-apply) ---
    ("INCIDENT", "inventory-sync", "autoscaling-change", "2026-01-15",
     "Min replicas 4->2 caused queue backlog during the morning sync window; 18 min delay."),
    ("INCIDENT", "fraud-scorer", "schema-change", "2026-02-19",
     "Renamed a feature column; scorer silently defaulted to score 0 for 9 min. Caught by canary."),
    ("NEARMISS", "auth-gateway", "retry-config", "2026-04-02",
     "Retry policy on SSO callback doubled login latency in staging. Reverted."),
    ("INCIDENT", "notification-worker", "dependency-bump", "2026-01-28",
     "SMS SDK minor bump changed default timeout; messages delayed 40 min before detection."),
    ("NEARMISS", "search-indexer", "dependency-bump", "2026-03-30",
     "Elasticsearch client bump failed integration tests on bulk API; blocked at CI."),
    ("INCIDENT", "checkout-web", "cache-ttl", "2026-06-02",
     "Product-page CDN TTL raised to 1h; price updates lagged during a promo."),
    ("NOTE", "search-indexer", "db-migration", "2026-04-11",
     "Index metadata tables are small (<2 GB) and migrated with online tooling; no user-facing writes depend on them."),
    ("NOTE", "notification-worker", "schema-change", "2026-05-14",
     "Message templates schema is additive-only by convention; consumers ignore unknown fields."),
    ("INCIDENT", "payments-service", "db-migration", "2026-02-24",
     "Adding an index on payments during business hours raised replica lag to 90s; refunds delayed."),
    ("NEARMISS", "fraud-scorer", "timeout-change", "2026-07-21",
     "Scorer timeout cut to 150ms would have fail-opened 4% of transactions; caught in load test."),
    ("INCIDENT", "notification-worker", "timeout-change", "2026-03-09",
     "Provider timeout lowered to 2s; push notifications dropped during provider slowness."),
    ("NEARMISS", "checkout-web", "dependency-bump", "2026-08-11",
     "Payment-widget SDK bump changed 3DS callback; caught in E2E tests."),
    ("INCIDENT", "search-indexer", "schema-change", "2026-01-22",
     "Mapping change forced a full reindex during peak; search results empty for 12 min."),
    ("NEARMISS", "ledger-api", "timeout-change", "2026-08-18",
     "v2 write-path timeout tweak flagged by soak test; not shipped."),
    ("INCIDENT", "fraud-scorer", "autoscaling-change", "2026-04-27",
     "Aggressive scale-down killed warm model replicas; cold-start latency spiked for 15 min."),
    ("NOTE", "payments-service", "feature-flag", "2026-06-15",
     "Payment flags use percentage rollouts (1/10/50/100) with automatic rollback on error-rate alarms."),
    ("NOTE", "fraud-scorer", "cache-ttl", "2026-05-30",
     "Feature cache TTL is advisory; scorer falls back to live lookups on miss."),
    ("NEARMISS", "auth-gateway", "dependency-bump", "2026-06-09",
     "JWT library bump changed clock-skew handling; caught in staging token tests."),
    ("INCIDENT", "inventory-sync", "schema-change", "2026-07-08",
     "Warehouse feed schema change broke ingest for one region for 27 min."),
    ("DEADEND", "inventory-sync", "cache-ttl", "2026-04-23",
     "Oversell incident: ruled out warehouse-API outage; feed was healthy, TTL alone caused the staleness."),
]

# ---------------------------------------------------------------- benchmark world
RISKY = [  # combos that genuinely cause incidents
    ("payments-service", "retry-config"), ("auth-gateway", "timeout-change"),
    ("inventory-sync", "cache-ttl"), ("checkout-web", "feature-flag"),
    ("fraud-scorer", "dependency-bump"),      # NOT in seed history: learned after first miss
    ("notification-worker", "autoscaling-change"),
]
SAFE_SCARY = [  # look risky generically, actually safe -> need human overrides
    ("search-indexer", "db-migration"), ("notification-worker", "schema-change"),
    ("search-indexer", "timeout-change"), ("ledger-api", "db-migration"),
    ("payments-service", "autoscaling-change"), ("checkout-web", "retry-config"),
]
QUIET = [("search-indexer", "feature-flag"), ("auth-gateway", "dependency-bump"),
         ("fraud-scorer", "cache-ttl")]
ALL_COMBOS = RISKY + SAFE_SCARY + QUIET
FLIP = (("payments-service", "autoscaling-change"), 30)  # becomes risky from change #30

OVERRIDE_REASONS = {
    ("search-indexer", "db-migration"): "Index metadata tables are tiny and migrate online; no user-facing writes affected.",
    ("notification-worker", "schema-change"): "Template schema is additive-only; consumers ignore unknown fields.",
    ("search-indexer", "timeout-change"): "Indexer is async and batch-driven; longer timeouts only slow reindex jobs.",
    ("ledger-api", "db-migration"): "v2 uses online migrations (rewrite shipped Jun 2026); the old lock-the-table lesson no longer applies.",
    ("payments-service", "autoscaling-change"): "Replica floor is unchanged; HPA bounds only affect burst capacity.",
    ("checkout-web", "retry-config"): "Client retry is idempotent and capped at 2 with jitter.",
    ("auth-gateway", "dependency-bump"): "JWT library is pinned and the clock-skew change was fixed upstream in 4.2; staging token tests now cover it.",
}
INCIDENT_TEXT = {
    ("fraud-scorer", "dependency-bump"): "Model-runtime bump changed feature dtype handling; scores drifted for 31 min before alerting.",
    ("payments-service", "autoscaling-change"): "New HPA ceiling exhausted the acquirer connection quota; 19 min of capture failures.",
}


def truth_risky(combo, idx):
    return combo in RISKY or (combo == FLIP[0] and idx >= FLIP[1])


def build_stream(seed=7, rounds=3):
    """46 changes: each combo appears once per round (shuffled) + one tail change after the regression."""
    rng = random.Random(seed)
    start = date(2026, 9, 1)
    combos, stream = list(ALL_COMBOS), []
    for _ in range(rounds):
        order = combos[:]
        rng.shuffle(order)
        for c in order:
            stream.append(c)
    stream.append(FLIP[0])
    out = []
    for i, (svc, pat) in enumerate(stream):
        d = start + timedelta(days=i)
        out.append({"i": i, "service": svc, "pattern": pat, "date": d.isoformat(),
                    "day": d.strftime("%a"),
                    "description": f"{pat.replace('-', ' ')} on {svc}"})
    return out


SCENARIOS = [
    {"title": "Longer inventory cache TTL", "service": "inventory-sync", "pattern": "cache-ttl", "day": "Tue",
     "description": "Raise stock-count cache TTL from 60s to 600s to reduce warehouse API load."},
    {"title": "Payment retries 3 to 5, on a Friday", "service": "payments-service", "pattern": "retry-config", "day": "Fri",
     "description": "Increase card-capture retry count from 3 to 5 with the same backoff."},
    {"title": "Online index migration on search", "service": "search-indexer", "pattern": "db-migration", "day": "Wed",
     "description": "Add a covering index to the index-metadata tables using online migration tooling."},
    {"title": "Ledger table migration (after v2 rewrite)", "service": "ledger-api", "pattern": "db-migration", "day": "Thu",
     "description": "Add a nullable column to ledger_entries via the v2 online migration path."},
]
