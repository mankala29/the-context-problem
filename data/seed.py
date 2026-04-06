"""
Seeds the versioned store with a realistic incident timeline.

Scenario: INC-001 — Database connection pool exhaustion causing API failures.

The incident evolves over 30 minutes. Each update is a new document version.
The experiment query is always:
    "What is the current status of INC-001 and what immediate action should be taken?"

The correct answer depends entirely on which version of the data is in the context.
"""

from data.store import VersionedStore

# Experiment timestamps (seconds from epoch t=0)
T0  = 0      # incident detected
T5  = 300    # root cause identified
T15 = 900    # fix deployed, monitoring
T30 = 1800   # fully resolved


def seed(store: VersionedStore) -> None:
    # ── INC-001: evolving incident record ─────────────────────────────────────

    store.write("INC-001", {
        "title": "API endpoints returning 503 errors",
        "severity": "P1",
        "status": "investigating",
        "affected_services": "all public API endpoints",
        "error_rate": "45%",
        "root_cause": "unknown",
        "current_action": "on-call engineer paged, investigation starting",
        "recommended_action": "all hands on deck, escalate to VP Engineering",
        "next_update_in": "5 minutes",
    }, timestamp=T0)

    store.write("INC-001", {
        "title": "API endpoints returning 503 errors",
        "severity": "P1",
        "status": "fix_in_progress",
        "affected_services": "all public API endpoints",
        "error_rate": "45%",
        "root_cause": "database connection pool exhausted — max 100 connections reached",
        "current_action": "restarting connection pool, deploying config patch",
        "recommended_action": "do not restart application servers yet — wait for pool reset",
        "next_update_in": "10 minutes",
    }, timestamp=T5)

    store.write("INC-001", {
        "title": "API endpoints returning 503 errors",
        "severity": "P2",
        "status": "monitoring",
        "affected_services": "partial — error rate dropping",
        "error_rate": "8%",
        "root_cause": "database connection pool exhausted — patch deployed",
        "current_action": "monitoring metrics, no further changes being made",
        "recommended_action": "hold all deploys for 15 minutes, watch error rate",
        "next_update_in": "15 minutes",
    }, timestamp=T15)

    store.write("INC-001", {
        "title": "API endpoints returning 503 errors",
        "severity": "P3",
        "status": "resolved",
        "affected_services": "none — fully recovered",
        "error_rate": "0%",
        "root_cause": "database connection pool exhausted — fixed via config patch",
        "current_action": "incident closed",
        "recommended_action": "schedule post-mortem, resume normal deploy schedule",
        "next_update_in": "N/A",
    }, timestamp=T30)

    # ── Runbook: static document, does not change ─────────────────────────────

    store.write("RUNBOOK-DB-POOL", {
        "title": "Database connection pool exhaustion runbook",
        "step_1": "check current connection count: SELECT count(*) FROM pg_stat_activity",
        "step_2": "identify long-running queries blocking connections",
        "step_3": "restart connection pooler (pgbouncer) — command: systemctl restart pgbouncer",
        "step_4": "apply config patch: max_connections=200 in pgbouncer.ini",
        "step_5": "monitor pg_stat_activity for 10 minutes post-fix",
        "escalation": "if error rate does not drop within 5 min of restart, page DBA team",
    }, timestamp=T0)

    # ── Service dependency map: updated once during incident ──────────────────

    store.write("SERVICE-MAP", {
        "api_gateway": "depends_on: auth-service, db-primary",
        "auth_service": "depends_on: db-primary",
        "db_primary": "status: degraded at T0, healthy at T15",
        "db_replica": "status: healthy throughout",
        "cache_layer": "status: healthy throughout",
    }, timestamp=T0)

    store.write("SERVICE-MAP", {
        "api_gateway": "depends_on: auth-service, db-primary",
        "auth_service": "depends_on: db-primary",
        "db_primary": "status: healthy — connection pool restored",
        "db_replica": "status: healthy",
        "cache_layer": "status: healthy",
    }, timestamp=T15)
