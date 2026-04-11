from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ActionExecution,
    AuditLog,
    ComplianceAttestation,
    ComplianceCase,
    DataSource,
    DataSourceStatus,
)
from app.schemas.pipeline import ScopeContext


OPEN_CASE_STATUSES = {"pending_approval", "executing"}
COMPLETED_CASE_STATUSES = {"completed", "rolled_back"}
ERROR_LATENCY_FLAGS = {"error", "timeout", "failed"}
ERROR_BLOCK_REASONS = {
    "system_error",
    "connector_error",
    "internal_error",
    "execution_error",
    "source_error",
}

CAPACITY_BASELINE_CONCURRENT_USERS = 100


def _iso_minute_bucket(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.replace(second=0, microsecond=0).isoformat()


class SystemAdminService:
    def get_fleet_health(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        lookback_hours: int,
    ) -> dict[str, object]:
        now = datetime.now(tz=UTC)
        since = now - timedelta(hours=lookback_hours)

        total_queries = int(
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.tenant_id == scope.tenant_id,
                    AuditLog.created_at >= since,
                )
            )
            or 0
        )
        blocked_queries = int(
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.tenant_id == scope.tenant_id,
                    AuditLog.created_at >= since,
                    AuditLog.was_blocked.is_(True),
                )
            )
            or 0
        )
        blocked_ratio = (
            round((blocked_queries / total_queries) * 100, 2)
            if total_queries > 0
            else 0.0
        )
        audit_rows = self._load_audit_rows(
            db=db,
            tenant_id=scope.tenant_id,
            from_at=since,
            limit=10000,
        )
        p95_latency_ms = self._percentile(
            [max(0, int(row.latency_ms or 0)) for row in audit_rows],
            95,
        )
        error_queries = sum(1 for row in audit_rows if self._is_query_error(row))
        error_query_rate = (
            round((error_queries / total_queries) * 100, 3)
            if total_queries > 0
            else 0.0
        )

        actions_executed = int(
            db.scalar(
                select(func.count())
                .select_from(ActionExecution)
                .where(
                    ActionExecution.tenant_id == scope.tenant_id,
                    ActionExecution.requested_at >= since,
                )
            )
            or 0
        )

        active_users_30d = int(
            db.scalar(
                select(func.count(func.distinct(AuditLog.user_id)))
                .where(
                    AuditLog.tenant_id == scope.tenant_id,
                    AuditLog.created_at >= (now - timedelta(days=30)),
                )
            )
            or 0
        )

        connector_rows = db.scalars(
            select(DataSource).where(DataSource.tenant_id == scope.tenant_id)
        ).all()
        connector_counts = Counter(str(row.status.value) for row in connector_rows)

        open_cases = int(
            db.scalar(
                select(func.count())
                .select_from(ComplianceCase)
                .where(
                    ComplianceCase.tenant_id == scope.tenant_id,
                    ComplianceCase.status.in_(OPEN_CASE_STATUSES),
                )
            )
            or 0
        )

        alerts: list[dict[str, object]] = []
        if connector_counts.get("error", 0) > 0:
            alerts.append(
                {
                    "severity": "critical",
                    "code": "CONNECTOR_ERRORS_DETECTED",
                    "message": "One or more connectors are currently in error state",
                    "count": connector_counts.get("error", 0),
                }
            )
        if total_queries >= 20 and blocked_ratio >= 25.0:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "HIGH_BLOCKED_QUERY_RATIO",
                    "message": "Blocked query ratio is above expected baseline",
                    "blocked_ratio_percent": blocked_ratio,
                }
            )
        if p95_latency_ms is not None and p95_latency_ms > 1000:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "HIGH_P95_LATENCY",
                    "message": "P95 query latency is above 1000ms target",
                    "p95_latency_ms": p95_latency_ms,
                }
            )
        if total_queries >= 20 and error_query_rate > 0.1:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "ELEVATED_QUERY_ERROR_RATE",
                    "message": "Error-like query event rate is above 0.1%",
                    "error_query_rate_percent": error_query_rate,
                }
            )
        if open_cases >= 10:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "COMPLIANCE_CASE_BACKLOG",
                    "message": "Open compliance case backlog is elevated",
                    "open_case_count": open_cases,
                }
            )

        overall_status = "healthy"
        if any(item["severity"] == "critical" for item in alerts):
            overall_status = "critical"
        elif alerts:
            overall_status = "degraded"

        return {
            "generated_at": now.isoformat(),
            "overall_status": overall_status,
            "window": {
                "lookback_hours": lookback_hours,
                "from": since.isoformat(),
                "to": now.isoformat(),
            },
            "activity": {
                "queries": total_queries,
                "blocked_queries": blocked_queries,
                "blocked_query_ratio_percent": blocked_ratio,
                "error_queries": error_queries,
                "error_query_rate_percent": error_query_rate,
                "actions_executed": actions_executed,
                "active_users_30d": active_users_30d,
            },
            "performance": {
                "p95_latency_ms": p95_latency_ms,
            },
            "connectors": {
                "total": len(connector_rows),
                "connected": connector_counts.get("connected", 0),
                "disconnected": connector_counts.get("disconnected", 0),
                "paused": connector_counts.get("paused", 0),
                "error": connector_counts.get("error", 0),
            },
            "compliance": {
                "open_cases": open_cases,
            },
            "alerts": alerts,
        }

    def get_tenant_deep_dive(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        window_days: int,
    ) -> dict[str, object]:
        now = datetime.now(tz=UTC)
        window_from = now - timedelta(days=window_days)

        total_queries = int(
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.tenant_id == scope.tenant_id,
                    AuditLog.created_at >= window_from,
                )
            )
            or 0
        )
        blocked_queries = int(
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.tenant_id == scope.tenant_id,
                    AuditLog.created_at >= window_from,
                    AuditLog.was_blocked.is_(True),
                )
            )
            or 0
        )

        actions = int(
            db.scalar(
                select(func.count())
                .select_from(ActionExecution)
                .where(
                    ActionExecution.tenant_id == scope.tenant_id,
                    ActionExecution.requested_at >= window_from,
                )
            )
            or 0
        )

        cases_total = int(
            db.scalar(
                select(func.count())
                .select_from(ComplianceCase)
                .where(ComplianceCase.tenant_id == scope.tenant_id)
            )
            or 0
        )
        attestations_total = int(
            db.scalar(
                select(func.count())
                .select_from(ComplianceAttestation)
                .where(ComplianceAttestation.tenant_id == scope.tenant_id)
            )
            or 0
        )

        connector_rows = db.scalars(
            select(DataSource).where(DataSource.tenant_id == scope.tenant_id)
        ).all()

        domain_counter: Counter[str] = Counter()
        recent_audit_rows = db.scalars(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == scope.tenant_id,
                AuditLog.created_at >= window_from,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(5000)
        ).all()
        for row in recent_audit_rows:
            for domain in list(row.domains_accessed or []):
                normalized = str(domain).strip().lower()
                if normalized:
                    domain_counter[normalized] += 1

        top_domains = [
            {"domain": domain, "query_events": count}
            for domain, count in domain_counter.most_common(5)
        ]

        avg_queries_per_day = round(total_queries / max(window_days, 1), 2)
        blocked_ratio = (
            round((blocked_queries / total_queries) * 100, 2)
            if total_queries > 0
            else 0.0
        )

        return {
            "generated_at": now.isoformat(),
            "tenant_id": scope.tenant_id,
            "window": {
                "days": window_days,
                "from": window_from.isoformat(),
                "to": now.isoformat(),
            },
            "usage": {
                "total_queries": total_queries,
                "blocked_queries": blocked_queries,
                "blocked_query_ratio_percent": blocked_ratio,
                "average_queries_per_day": avg_queries_per_day,
                "top_domains": top_domains,
            },
            "execution": {
                "actions_executed": actions,
            },
            "compliance": {
                "cases_total": cases_total,
                "attestations_total": attestations_total,
            },
            "connectors": [
                {
                    "id": row.id,
                    "name": row.name,
                    "source_type": row.source_type.value,
                    "status": row.status.value,
                    "last_sync_at": row.last_sync_at.isoformat()
                    if row.last_sync_at
                    else None,
                }
                for row in connector_rows
            ],
        }

    def get_churn_risk(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        window_days: int,
    ) -> dict[str, object]:
        now = datetime.now(tz=UTC)
        half_window_days = max(window_days // 2, 1)

        recent_from = now - timedelta(days=half_window_days)
        prior_from = recent_from - timedelta(days=half_window_days)

        recent_queries = self._count_queries(
            db=db,
            tenant_id=scope.tenant_id,
            from_at=recent_from,
            to_at=now,
        )
        prior_queries = self._count_queries(
            db=db,
            tenant_id=scope.tenant_id,
            from_at=prior_from,
            to_at=recent_from,
        )

        recent_active_users = self._count_distinct_users(
            db=db,
            tenant_id=scope.tenant_id,
            from_at=recent_from,
            to_at=now,
        )
        prior_active_users = self._count_distinct_users(
            db=db,
            tenant_id=scope.tenant_id,
            from_at=prior_from,
            to_at=recent_from,
        )

        connector_errors = int(
            db.scalar(
                select(func.count())
                .select_from(DataSource)
                .where(
                    DataSource.tenant_id == scope.tenant_id,
                    DataSource.status == DataSourceStatus.error,
                )
            )
            or 0
        )

        signals: list[dict[str, object]] = []
        score = 0.0

        if prior_queries > 0:
            decline_ratio = max((prior_queries - recent_queries) / prior_queries, 0.0)
            if decline_ratio >= 0.5:
                score += 4.0
                signals.append(
                    {
                        "code": "QUERY_VOLUME_DECLINE",
                        "severity": "high",
                        "message": "Query volume declined by 50% or more",
                        "value": round(decline_ratio * 100, 2),
                    }
                )
            elif decline_ratio >= 0.25:
                score += 2.5
                signals.append(
                    {
                        "code": "QUERY_VOLUME_DECLINE",
                        "severity": "medium",
                        "message": "Query volume declined by 25% or more",
                        "value": round(decline_ratio * 100, 2),
                    }
                )

        if prior_active_users > 0:
            active_user_decline = max(
                (prior_active_users - recent_active_users) / prior_active_users,
                0.0,
            )
            if active_user_decline >= 0.4:
                score += 2.5
                signals.append(
                    {
                        "code": "ACTIVE_USER_DECLINE",
                        "severity": "medium",
                        "message": "Active user base declined sharply",
                        "value": round(active_user_decline * 100, 2),
                    }
                )

        if connector_errors > 0:
            score += min(3.0, connector_errors * 1.5)
            signals.append(
                {
                    "code": "CONNECTOR_INSTABILITY",
                    "severity": "high",
                    "message": "Connectors in error state may impact adoption",
                    "value": connector_errors,
                }
            )

        risk_score = round(min(score, 10.0), 2)
        if risk_score >= 7.0:
            risk_level = "high"
        elif risk_score >= 4.0:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "generated_at": now.isoformat(),
            "tenant_id": scope.tenant_id,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "window_days": window_days,
            "metrics": {
                "recent_queries": recent_queries,
                "prior_queries": prior_queries,
                "recent_active_users": recent_active_users,
                "prior_active_users": prior_active_users,
                "connector_errors": connector_errors,
            },
            "signals": signals,
        }

    def get_llm_cost_analytics(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        window_days: int,
        estimated_cost_per_query: float,
    ) -> dict[str, object]:
        now = datetime.now(tz=UTC)
        window_from = now - timedelta(days=window_days)

        total_queries = int(
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.tenant_id == scope.tenant_id,
                    AuditLog.created_at >= window_from,
                )
            )
            or 0
        )

        total_spend = round(total_queries * estimated_cost_per_query, 4)
        avg_daily_queries = total_queries / max(window_days, 1)

        domain_counter: Counter[str] = Counter()
        rows = db.scalars(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == scope.tenant_id,
                AuditLog.created_at >= window_from,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(5000)
        ).all()
        for row in rows:
            for domain in list(row.domains_accessed or []):
                normalized = str(domain).strip().lower()
                if normalized:
                    domain_counter[normalized] += 1

        spend_by_domain = []
        for domain, query_events in domain_counter.most_common(10):
            spend_by_domain.append(
                {
                    "domain": domain,
                    "query_events": query_events,
                    "estimated_spend": round(query_events * estimated_cost_per_query, 4),
                }
            )

        projected_monthly_queries = round(avg_daily_queries * 30)
        projected_monthly_spend = round(
            projected_monthly_queries * estimated_cost_per_query,
            2,
        )

        return {
            "generated_at": now.isoformat(),
            "tenant_id": scope.tenant_id,
            "window": {
                "days": window_days,
                "from": window_from.isoformat(),
                "to": now.isoformat(),
            },
            "cost_model": {
                "estimated_cost_per_query": estimated_cost_per_query,
                "currency": "USD",
            },
            "summary": {
                "total_queries": total_queries,
                "estimated_total_spend": total_spend,
                "average_queries_per_day": round(avg_daily_queries, 2),
                "projected_monthly_spend": projected_monthly_spend,
            },
            "breakdown": {
                "top_domains": spend_by_domain,
            },
            "optimization_opportunities": [
                {
                    "code": "INCREASE_INTENT_CACHE_HIT_RATE",
                    "description": "Increase cache reuse for repeated prompts to reduce LLM calls",
                    "estimated_monthly_savings": round(projected_monthly_spend * 0.12, 2),
                },
                {
                    "code": "PROMPT_COMPRESSION",
                    "description": "Reduce prompt token footprint through compact templates",
                    "estimated_monthly_savings": round(projected_monthly_spend * 0.08, 2),
                },
            ],
        }

    def get_slo_compliance(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        window_days: int,
        latency_target_ms: int,
        error_budget_percent: float,
        dsar_slo_days: int,
    ) -> dict[str, object]:
        now = datetime.now(tz=UTC)
        window_from = now - timedelta(days=window_days)

        audit_rows = self._load_audit_rows(
            db=db,
            tenant_id=scope.tenant_id,
            from_at=window_from,
            limit=25000,
        )
        total_queries = len(audit_rows)
        blocked_queries = sum(1 for row in audit_rows if bool(row.was_blocked))
        error_queries = sum(1 for row in audit_rows if self._is_query_error(row))

        latency_values = [max(0, int(row.latency_ms or 0)) for row in audit_rows]
        p95_latency_ms = self._percentile(latency_values, 95)
        p99_latency_ms = self._percentile(latency_values, 99)

        error_rate_percent = (
            round((error_queries / total_queries) * 100, 3)
            if total_queries > 0
            else 0.0
        )
        blocked_ratio_percent = (
            round((blocked_queries / total_queries) * 100, 3)
            if total_queries > 0
            else 0.0
        )
        availability_percent = (
            round(((total_queries - error_queries) / total_queries) * 100, 3)
            if total_queries > 0
            else 100.0
        )

        completed_dsar_rows = db.scalars(
            select(ComplianceCase)
            .where(
                ComplianceCase.tenant_id == scope.tenant_id,
                ComplianceCase.case_type == "dsar",
                ComplianceCase.status == "completed",
                ComplianceCase.requested_at >= window_from,
            )
            .order_by(ComplianceCase.requested_at.desc())
        ).all()

        turnaround_days: list[float] = []
        on_time_count = 0
        for row in completed_dsar_rows:
            duration_days = max(
                (row.updated_at - row.requested_at).total_seconds() / 86400.0,
                0.0,
            )
            turnaround_days.append(round(duration_days, 4))
            if duration_days <= dsar_slo_days:
                on_time_count += 1

        average_dsar_turnaround_days = (
            round(sum(turnaround_days) / len(turnaround_days), 3)
            if turnaround_days
            else None
        )
        dsar_on_time_rate_percent = (
            round((on_time_count / len(turnaround_days)) * 100, 2)
            if turnaround_days
            else None
        )

        open_sla_breaches = int(
            db.scalar(
                select(func.count())
                .select_from(ComplianceCase)
                .where(
                    ComplianceCase.tenant_id == scope.tenant_id,
                    ComplianceCase.sla_due_at < now,
                    ComplianceCase.status.notin_(COMPLETED_CASE_STATUSES),
                )
            )
            or 0
        )

        checks: list[dict[str, object]] = []

        latency_met = p95_latency_ms is None or p95_latency_ms <= latency_target_ms
        checks.append(
            {
                "code": "LATENCY_P95",
                "met": latency_met,
                "target": latency_target_ms,
                "actual": p95_latency_ms,
                "unit": "ms",
            }
        )

        error_met = error_rate_percent <= error_budget_percent
        checks.append(
            {
                "code": "ERROR_RATE",
                "met": error_met,
                "target": error_budget_percent,
                "actual": error_rate_percent,
                "unit": "percent",
            }
        )

        dsar_met = (
            True
            if dsar_on_time_rate_percent is None
            else dsar_on_time_rate_percent >= 95.0
        )
        checks.append(
            {
                "code": "DSAR_ON_TIME_COMPLETION",
                "met": dsar_met,
                "target": 95.0,
                "actual": dsar_on_time_rate_percent,
                "unit": "percent",
            }
        )

        breach_met = open_sla_breaches == 0
        checks.append(
            {
                "code": "OPEN_COMPLIANCE_SLA_BREACHES",
                "met": breach_met,
                "target": 0,
                "actual": open_sla_breaches,
                "unit": "count",
            }
        )

        if all(item["met"] for item in checks):
            overall_status = "met"
        elif any(item["code"] in {"LATENCY_P95", "ERROR_RATE"} and not item["met"] for item in checks):
            overall_status = "breached"
        else:
            overall_status = "at_risk"

        return {
            "generated_at": now.isoformat(),
            "tenant_id": scope.tenant_id,
            "window": {
                "days": window_days,
                "from": window_from.isoformat(),
                "to": now.isoformat(),
            },
            "targets": {
                "latency_p95_ms": latency_target_ms,
                "error_rate_percent": error_budget_percent,
                "dsar_slo_days": dsar_slo_days,
            },
            "observed": {
                "total_queries": total_queries,
                "blocked_queries": blocked_queries,
                "blocked_query_ratio_percent": blocked_ratio_percent,
                "error_queries": error_queries,
                "error_rate_percent": error_rate_percent,
                "availability_percent": availability_percent,
                "latency_p95_ms": p95_latency_ms,
                "latency_p99_ms": p99_latency_ms,
                "completed_dsar_cases": len(turnaround_days),
                "average_dsar_turnaround_days": average_dsar_turnaround_days,
                "dsar_on_time_rate_percent": dsar_on_time_rate_percent,
                "open_compliance_sla_breaches": open_sla_breaches,
            },
            "checks": checks,
            "overall_status": overall_status,
        }

    def get_capacity_model(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        window_days: int,
        target_p95_ms: int,
    ) -> dict[str, object]:
        now = datetime.now(tz=UTC)
        window_from = now - timedelta(days=window_days)

        audit_rows = self._load_audit_rows(
            db=db,
            tenant_id=scope.tenant_id,
            from_at=window_from,
            limit=50000,
        )

        total_queries = len(audit_rows)
        duration_minutes = max(window_days * 24 * 60, 1)
        avg_queries_per_minute = round(total_queries / duration_minutes, 4)

        latency_values = [max(0, int(row.latency_ms or 0)) for row in audit_rows]
        p95_latency_ms = self._percentile(latency_values, 95)

        query_minute_counts: Counter[str] = Counter()
        active_users_per_minute: dict[str, set[str]] = {}
        for row in audit_rows:
            minute_key = _iso_minute_bucket(row.created_at)
            query_minute_counts[minute_key] += 1
            users = active_users_per_minute.setdefault(minute_key, set())
            users.add(str(row.user_id))

        peak_queries_per_minute = max(query_minute_counts.values(), default=0)
        peak_active_users_per_minute = max(
            (len(users) for users in active_users_per_minute.values()),
            default=0,
        )

        latency_penalty = 1.0
        if p95_latency_ms is not None and p95_latency_ms > target_p95_ms:
            latency_penalty = max(target_p95_ms / max(p95_latency_ms, 1), 0.2)

        estimated_max_concurrent_users = max(
            int(round(CAPACITY_BASELINE_CONCURRENT_USERS * latency_penalty)),
            10,
        )

        observed_concurrency = peak_active_users_per_minute
        if observed_concurrency <= 0:
            headroom_percent = 100.0
        else:
            headroom_percent = round(
                ((estimated_max_concurrent_users - observed_concurrency) / estimated_max_concurrent_users)
                * 100,
                2,
            )

        if headroom_percent < 0:
            capacity_status = "over_capacity"
        elif headroom_percent <= 15:
            capacity_status = "near_capacity"
        else:
            capacity_status = "healthy"

        recommendations: list[str] = []
        if capacity_status in {"near_capacity", "over_capacity"}:
            recommendations.append(
                "Increase query-cache hit ratio and warm hot intent keys"
            )
            recommendations.append(
                "Enable priority routing for interactive workloads"
            )
        if p95_latency_ms is not None and p95_latency_ms > target_p95_ms:
            recommendations.append(
                "Tune connector/database indexes to bring P95 under target"
            )
        if not recommendations:
            recommendations.append("Current capacity posture is healthy")

        return {
            "generated_at": now.isoformat(),
            "tenant_id": scope.tenant_id,
            "window": {
                "days": window_days,
                "from": window_from.isoformat(),
                "to": now.isoformat(),
            },
            "targets": {
                "p95_latency_ms": target_p95_ms,
                "baseline_concurrent_users": CAPACITY_BASELINE_CONCURRENT_USERS,
            },
            "observed": {
                "total_queries": total_queries,
                "avg_queries_per_minute": avg_queries_per_minute,
                "peak_queries_per_minute": peak_queries_per_minute,
                "peak_active_users_per_minute": peak_active_users_per_minute,
                "p95_latency_ms": p95_latency_ms,
            },
            "model": {
                "estimated_max_concurrent_users": estimated_max_concurrent_users,
                "observed_peak_concurrent_users": observed_concurrency,
                "headroom_percent": headroom_percent,
                "capacity_status": capacity_status,
                "recommendations": recommendations,
            },
        }

    def get_degradation_policy_status(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        lookback_hours: int,
        warning_p95_ms: int,
        critical_p95_ms: int,
        warning_error_rate_percent: float,
        critical_error_rate_percent: float,
        warning_pending_actions: int,
        critical_pending_actions: int,
    ) -> dict[str, object]:
        now = datetime.now(tz=UTC)
        since = now - timedelta(hours=lookback_hours)

        audit_rows = self._load_audit_rows(
            db=db,
            tenant_id=scope.tenant_id,
            from_at=since,
            limit=30000,
        )

        total_queries = len(audit_rows)
        latency_values = [max(0, int(row.latency_ms or 0)) for row in audit_rows]
        p95_latency_ms = self._percentile(latency_values, 95)
        error_queries = sum(1 for row in audit_rows if self._is_query_error(row))
        error_rate_percent = (
            round((error_queries / total_queries) * 100, 3)
            if total_queries > 0
            else 0.0
        )

        pending_actions = int(
            db.scalar(
                select(func.count())
                .select_from(ActionExecution)
                .where(
                    ActionExecution.tenant_id == scope.tenant_id,
                    ActionExecution.status.in_({"awaiting_approval", "executing"}),
                )
            )
            or 0
        )

        critical_triggered = (
            (p95_latency_ms is not None and p95_latency_ms >= critical_p95_ms)
            or error_rate_percent >= critical_error_rate_percent
            or pending_actions >= critical_pending_actions
        )
        warning_triggered = (
            (p95_latency_ms is not None and p95_latency_ms >= warning_p95_ms)
            or error_rate_percent >= warning_error_rate_percent
            or pending_actions >= warning_pending_actions
        )

        if critical_triggered:
            mode = "critical"
            controls = [
                "Activate strict priority routing for interactive and compliance actions",
                "Throttle bulk/reporting workloads",
                "Increase worker concurrency and connector pool sizes",
            ]
        elif warning_triggered:
            mode = "degraded"
            controls = [
                "Enable soft priority routing for interactive workloads",
                "Apply backpressure to non-critical batch jobs",
            ]
        else:
            mode = "normal"
            controls = ["No degradation controls required"]

        return {
            "generated_at": now.isoformat(),
            "tenant_id": scope.tenant_id,
            "window": {
                "lookback_hours": lookback_hours,
                "from": since.isoformat(),
                "to": now.isoformat(),
            },
            "policy_thresholds": {
                "warning": {
                    "p95_latency_ms": warning_p95_ms,
                    "error_rate_percent": warning_error_rate_percent,
                    "pending_actions": warning_pending_actions,
                },
                "critical": {
                    "p95_latency_ms": critical_p95_ms,
                    "error_rate_percent": critical_error_rate_percent,
                    "pending_actions": critical_pending_actions,
                },
            },
            "signals": {
                "queries": total_queries,
                "p95_latency_ms": p95_latency_ms,
                "error_rate_percent": error_rate_percent,
                "pending_actions": pending_actions,
            },
            "degradation_mode": mode,
            "controls": controls,
        }

    def get_performance_regression(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        window_hours: int,
        max_p95_regression_percent: float,
        max_p99_regression_percent: float,
        max_error_rate_percent: float,
    ) -> dict[str, object]:
        now = datetime.now(tz=UTC)
        recent_from = now - timedelta(hours=window_hours)
        baseline_from = recent_from - timedelta(hours=window_hours)

        recent_rows = db.scalars(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == scope.tenant_id,
                AuditLog.created_at >= recent_from,
                AuditLog.created_at < now,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(50000)
        ).all()
        baseline_rows = db.scalars(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == scope.tenant_id,
                AuditLog.created_at >= baseline_from,
                AuditLog.created_at < recent_from,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(50000)
        ).all()

        recent_metrics = self._build_performance_window_metrics(recent_rows)
        baseline_metrics = self._build_performance_window_metrics(baseline_rows)

        p95_regression_percent = self._compute_regression_percent(
            baseline=baseline_metrics["latency_p95_ms"],
            current=recent_metrics["latency_p95_ms"],
        )
        p99_regression_percent = self._compute_regression_percent(
            baseline=baseline_metrics["latency_p99_ms"],
            current=recent_metrics["latency_p99_ms"],
        )

        checks = [
            {
                "code": "P95_REGRESSION",
                "met": p95_regression_percent is None
                or p95_regression_percent <= max_p95_regression_percent,
                "threshold": max_p95_regression_percent,
                "actual": p95_regression_percent,
                "unit": "percent",
            },
            {
                "code": "P99_REGRESSION",
                "met": p99_regression_percent is None
                or p99_regression_percent <= max_p99_regression_percent,
                "threshold": max_p99_regression_percent,
                "actual": p99_regression_percent,
                "unit": "percent",
            },
            {
                "code": "ERROR_RATE_BUDGET",
                "met": recent_metrics["error_rate_percent"] <= max_error_rate_percent,
                "threshold": max_error_rate_percent,
                "actual": recent_metrics["error_rate_percent"],
                "unit": "percent",
            },
        ]

        if all(item["met"] for item in checks):
            overall_status = "stable"
            recommendation = "Current release profile is stable against baseline"
        else:
            overall_status = "regressed"
            recommendation = (
                "Hold rollout and investigate latency/error regressions before promoting"
            )

        return {
            "generated_at": now.isoformat(),
            "tenant_id": scope.tenant_id,
            "windows": {
                "recent": {
                    "hours": window_hours,
                    "from": recent_from.isoformat(),
                    "to": now.isoformat(),
                },
                "baseline": {
                    "hours": window_hours,
                    "from": baseline_from.isoformat(),
                    "to": recent_from.isoformat(),
                },
            },
            "thresholds": {
                "max_p95_regression_percent": max_p95_regression_percent,
                "max_p99_regression_percent": max_p99_regression_percent,
                "max_error_rate_percent": max_error_rate_percent,
            },
            "metrics": {
                "recent": recent_metrics,
                "baseline": baseline_metrics,
                "delta": {
                    "p95_regression_percent": p95_regression_percent,
                    "p99_regression_percent": p99_regression_percent,
                    "error_rate_delta_percent": round(
                        recent_metrics["error_rate_percent"]
                        - baseline_metrics["error_rate_percent"],
                        3,
                    ),
                },
            },
            "checks": checks,
            "overall_status": overall_status,
            "recommendation": recommendation,
        }

    def get_alerts(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        lookback_hours: int,
    ) -> dict[str, object]:
        now = datetime.now(tz=UTC)
        since = now - timedelta(hours=lookback_hours)

        audit_rows = self._load_audit_rows(
            db=db,
            tenant_id=scope.tenant_id,
            from_at=since,
            limit=20000,
        )
        total_queries = len(audit_rows)
        blocked_queries = sum(1 for row in audit_rows if bool(row.was_blocked))
        blocked_ratio = (
            round((blocked_queries / total_queries) * 100, 2)
            if total_queries > 0
            else 0.0
        )
        error_queries = sum(1 for row in audit_rows if self._is_query_error(row))
        error_rate = (
            round((error_queries / total_queries) * 100, 3)
            if total_queries > 0
            else 0.0
        )
        p95_latency = self._percentile(
            [max(0, int(row.latency_ms or 0)) for row in audit_rows],
            95,
        )

        connector_error_count = int(
            db.scalar(
                select(func.count())
                .select_from(DataSource)
                .where(
                    DataSource.tenant_id == scope.tenant_id,
                    DataSource.status == DataSourceStatus.error,
                )
            )
            or 0
        )
        overdue_approvals = int(
            db.scalar(
                select(func.count())
                .select_from(ActionExecution)
                .where(
                    ActionExecution.tenant_id == scope.tenant_id,
                    ActionExecution.status == "awaiting_approval",
                    ActionExecution.approval_due_at.is_not(None),
                    ActionExecution.approval_due_at < now,
                )
            )
            or 0
        )
        compliance_sla_breaches = int(
            db.scalar(
                select(func.count())
                .select_from(ComplianceCase)
                .where(
                    ComplianceCase.tenant_id == scope.tenant_id,
                    ComplianceCase.sla_due_at < now,
                    ComplianceCase.status.notin_(COMPLETED_CASE_STATUSES),
                )
            )
            or 0
        )

        alerts: list[dict[str, object]] = []
        if connector_error_count > 0:
            alerts.append(
                {
                    "severity": "critical",
                    "code": "CONNECTOR_ERRORS_DETECTED",
                    "message": "One or more connectors are currently in error state",
                    "count": connector_error_count,
                    "suggested_action": "Run connector diagnostics and notify impacted tenant owners",
                }
            )
        if p95_latency is not None and p95_latency > 1000:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "P95_LATENCY_TARGET_BREACH",
                    "message": "P95 query latency exceeded 1000ms in current window",
                    "p95_latency_ms": p95_latency,
                    "suggested_action": "Inspect slow query traces and connector latency",
                }
            )
        if error_rate > 0.1:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "QUERY_ERROR_BUDGET_EXCEEDED",
                    "message": "Error-like query rate is above the 0.1% target",
                    "error_rate_percent": error_rate,
                    "suggested_action": "Review failure logs and source availability",
                }
            )
        if blocked_ratio >= 25.0 and total_queries >= 20:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "HIGH_POLICY_DENY_RATIO",
                    "message": "Blocked query ratio is above 25%",
                    "blocked_ratio_percent": blocked_ratio,
                    "suggested_action": "Review policy drift and user guidance",
                }
            )
        if overdue_approvals > 0:
            alerts.append(
                {
                    "severity": "warning",
                    "code": "OVERDUE_APPROVAL_QUEUE",
                    "message": "One or more approval-required actions are overdue",
                    "count": overdue_approvals,
                    "suggested_action": "Escalate to approvers or re-route approvals",
                }
            )
        if compliance_sla_breaches > 0:
            alerts.append(
                {
                    "severity": "critical",
                    "code": "COMPLIANCE_SLA_BREACHES",
                    "message": "Open compliance cases are past SLA",
                    "count": compliance_sla_breaches,
                    "suggested_action": "Prioritize breach case remediation immediately",
                }
            )

        severity_rank = {"critical": 0, "warning": 1, "info": 2}
        alerts.sort(key=lambda item: severity_rank.get(str(item.get("severity")), 3))

        return {
            "generated_at": now.isoformat(),
            "tenant_id": scope.tenant_id,
            "window": {
                "lookback_hours": lookback_hours,
                "from": since.isoformat(),
                "to": now.isoformat(),
            },
            "summary": {
                "total_alerts": len(alerts),
                "critical": sum(1 for item in alerts if item["severity"] == "critical"),
                "warning": sum(1 for item in alerts if item["severity"] == "warning"),
            },
            "signals": {
                "queries": total_queries,
                "blocked_query_ratio_percent": blocked_ratio,
                "error_query_rate_percent": error_rate,
                "p95_latency_ms": p95_latency,
                "connector_errors": connector_error_count,
                "overdue_approvals": overdue_approvals,
                "compliance_sla_breaches": compliance_sla_breaches,
            },
            "alerts": alerts,
        }

    @staticmethod
    def _count_queries(
        *,
        db: Session,
        tenant_id: str,
        from_at: datetime,
        to_at: datetime,
    ) -> int:
        return int(
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.created_at >= from_at,
                    AuditLog.created_at < to_at,
                )
            )
            or 0
        )

    @staticmethod
    def _count_distinct_users(
        *,
        db: Session,
        tenant_id: str,
        from_at: datetime,
        to_at: datetime,
    ) -> int:
        return int(
            db.scalar(
                select(func.count(func.distinct(AuditLog.user_id))).where(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.created_at >= from_at,
                    AuditLog.created_at < to_at,
                )
            )
            or 0
        )

    @staticmethod
    def _load_audit_rows(
        *,
        db: Session,
        tenant_id: str,
        from_at: datetime,
        limit: int,
    ) -> list[AuditLog]:
        return db.scalars(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == tenant_id,
                AuditLog.created_at >= from_at,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        ).all()

    @staticmethod
    def _is_query_error(row: AuditLog) -> bool:
        latency_flag = (row.latency_flag or "").strip().lower()
        block_reason = (row.block_reason or "").strip().lower()
        return (
            latency_flag in ERROR_LATENCY_FLAGS
            or block_reason in ERROR_BLOCK_REASONS
        )

    def _build_performance_window_metrics(
        self,
        rows: list[AuditLog],
    ) -> dict[str, float | int | None]:
        total_queries = len(rows)
        latency_values = [max(0, int(row.latency_ms or 0)) for row in rows]
        error_queries = sum(1 for row in rows if self._is_query_error(row))

        return {
            "total_queries": total_queries,
            "latency_p95_ms": self._percentile(latency_values, 95),
            "latency_p99_ms": self._percentile(latency_values, 99),
            "latency_avg_ms": round(sum(latency_values) / total_queries, 3)
            if total_queries > 0
            else None,
            "error_queries": error_queries,
            "error_rate_percent": round((error_queries / total_queries) * 100, 3)
            if total_queries > 0
            else 0.0,
        }

    @staticmethod
    def _compute_regression_percent(
        *,
        baseline: int | None,
        current: int | None,
    ) -> float | None:
        if baseline is None or current is None:
            return None
        if baseline <= 0:
            return None
        return round(((current - baseline) / baseline) * 100, 3)

    @staticmethod
    def _percentile(values: list[int], percentile: int) -> int | None:
        if not values:
            return None

        sorted_values = sorted(values)
        if len(sorted_values) == 1:
            return sorted_values[0]

        rank = (percentile / 100) * (len(sorted_values) - 1)
        lower_index = int(rank)
        upper_index = min(lower_index + 1, len(sorted_values) - 1)
        weight = rank - lower_index

        lower = sorted_values[lower_index]
        upper = sorted_values[upper_index]
        interpolated = lower + (upper - lower) * weight
        return int(round(interpolated))


system_admin_service = SystemAdminService()
