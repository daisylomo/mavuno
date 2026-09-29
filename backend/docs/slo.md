# Service objectives and alerts

Measure objectives at the public API boundary and exclude only announced maintenance. Review these
initial targets after four weeks of representative production traffic.

| User outcome | SLO (rolling 30 days) | Page when |
| --- | --- | --- |
| API availability | 99.9% of non-health requests are not 5xx | 5-minute burn exceeds 14.4x or 1-hour burn exceeds 6x |
| Interactive latency | 95% of non-provider requests finish within 750 ms | p95 exceeds 1.5 s for 10 minutes |
| Payment correctness | 99.99% have one terminal ledger outcome | any duplicate capture or mismatch occurs |
| Message delivery | 99% are poll-visible within 5 seconds | p95 exceeds 15 seconds for 10 minutes |
| Background work | 99% of outbox jobs finish within 5 minutes | oldest ready job exceeds 10 minutes |

Alerts describe user-visible symptoms: sustained 5xx responses, readiness loss, latency,
reconciliation mismatch, stale outbox work, or exhausted dead-letter retries. CPU, memory,
connection-pool, cache, and query-budget signals are diagnostic context. Dashboards split status
class and bounded route template, never raw URLs, user IDs, phone numbers, or listing IDs.

Each page links to `operations.md`, names an owner and severity, and carries request/trace IDs plus
the deployed image digest. Synthetic probes exercise liveness, readiness, catalog browse, and a
non-mutating authenticated request from Nairobi and the primary hosting region.
