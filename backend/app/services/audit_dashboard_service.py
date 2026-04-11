from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditLog
from app.schemas.pipeline import ScopeContext


ERROR_LATENCY_FLAGS = {"error", "timeout", "failed"}


class AuditDashboardService:
    def get_dashboard(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        window_hours: int,
        anomaly_limit: int,
    ) -> dict[str, object]:
        now = datetime.now(tz=UTC)
        window_from = now - timedelta(hours=window_hours)

        rows = db.scalars(
            select(AuditLog)
            .where(
                AuditLog.tenant_id == scope.tenant_id,
                AuditLog.created_at >= window_from,
            )
            .order_by(AuditLog.created_at.desc())
            .limit(50000)
        ).all()

        total_events = len(rows)
        blocked_events = sum(1 for row in rows if bool(row.was_blocked))
        allowed_events = max(total_events - blocked_events, 0)

        blocked_ratio_percent = (
            round((blocked_events / total_events) * 100, 2)
            if total_events > 0
            else 0.0
        )

        error_like_events = sum(1 for row in rows if self._is_error_like(row))
        error_like_rate_percent = (
            round((error_like_events / total_events) * 100, 3)
            if total_events > 0
            else 0.0
        )

        unique_users = len({str(row.user_id) for row in rows})

        latencies = [max(0, int(row.latency_ms or 0)) for row in rows]
        avg_latency_ms = round(sum(latencies) / len(latencies), 2) if latencies else None
        p95_latency_ms = self._percentile(latencies, 95)

        domain_counter: Counter[str] = Counter()
        user_event_counter: Counter[str] = Counter()
        blocked_by_user_counter: Counter[str] = Counter()
        block_reason_counter: Counter[str] = Counter()
        out_of_hours_events = 0

        for row in rows:
            user_id = str(row.user_id)
            user_event_counter[user_id] += 1
            if bool(row.was_blocked):
                blocked_by_user_counter[user_id] += 1
                reason = (row.block_reason or "unknown").strip().lower()
                block_reason_counter[reason] += 1

            created_at = self._ensure_utc(row.created_at)
            if created_at.hour < 6 or created_at.hour >= 21:
                out_of_hours_events += 1

            for domain in list(row.domains_accessed or []):
                normalized = str(domain).strip().lower()
                if normalized:
                    domain_counter[normalized] += 1

        top_domains = [
            {"domain": domain, "events": count}
            for domain, count in domain_counter.most_common(5)
        ]

        top_active_users = [
            {
                "user_id": user_id,
                "event_count": event_count,
                "blocked_count": blocked_by_user_counter.get(user_id, 0),
            }
            for user_id, event_count in user_event_counter.most_common(5)
        ]

        top_block_reasons = [
            {"reason": reason, "count": count}
            for reason, count in block_reason_counter.most_common(5)
        ]

        anomalies: list[dict[str, object]] = []
        if total_events >= 20 and blocked_ratio_percent >= 25.0:
            anomalies.append(
                {
                    "code": "HIGH_BLOCKED_QUERY_RATIO",
                    "severity": "warning",
                    "message": "Blocked query ratio exceeded 25% in current window",
                    "value": blocked_ratio_percent,
                    "unit": "percent",
                }
            )

        if total_events >= 20 and error_like_rate_percent > 0.1:
            anomalies.append(
                {
                    "code": "ERROR_FLAG_BUDGET_EXCEEDED",
                    "severity": "warning",
                    "message": "Error-like event rate exceeded 0.1%",
                    "value": error_like_rate_percent,
                    "unit": "percent",
                }
            )

        if p95_latency_ms is not None and p95_latency_ms > 1000:
            anomalies.append(
                {
                    "code": "P95_LATENCY_TARGET_BREACH",
                    "severity": "warning",
                    "message": "P95 latency exceeded 1000ms",
                    "value": p95_latency_ms,
                    "unit": "ms",
                }
            )

        if out_of_hours_events >= 5:
            anomalies.append(
                {
                    "code": "ELEVATED_OUT_OF_HOURS_ACTIVITY",
                    "severity": "info",
                    "message": "Out-of-hours access activity is above baseline",
                    "value": out_of_hours_events,
                    "unit": "events",
                }
            )

        for user_id, blocked_count in blocked_by_user_counter.most_common(5):
            if blocked_count >= 5:
                anomalies.append(
                    {
                        "code": "REPEATED_POLICY_DENIALS_BY_USER",
                        "severity": "warning",
                        "message": "User has repeated blocked access attempts",
                        "user_id": user_id,
                        "value": blocked_count,
                        "unit": "events",
                    }
                )

        if user_event_counter:
            top_user_id, top_user_events = user_event_counter.most_common(1)[0]
            high_activity_threshold = max(25, int(total_events * 0.45))
            if top_user_events >= high_activity_threshold:
                anomalies.append(
                    {
                        "code": "CONCENTRATED_ACTIVITY_SINGLE_USER",
                        "severity": "info",
                        "message": "A single user generated an unusually high share of audit events",
                        "user_id": top_user_id,
                        "value": top_user_events,
                        "unit": "events",
                    }
                )

        severity_rank = {"warning": 0, "info": 1}
        anomalies.sort(key=lambda item: severity_rank.get(str(item.get("severity")), 2))

        return {
            "generated_at": now.isoformat(),
            "tenant_id": scope.tenant_id,
            "window": {
                "hours": window_hours,
                "from": window_from.isoformat(),
                "to": now.isoformat(),
            },
            "summary": {
                "total_events": total_events,
                "allowed_events": allowed_events,
                "blocked_events": blocked_events,
                "blocked_ratio_percent": blocked_ratio_percent,
                "error_like_events": error_like_events,
                "error_like_rate_percent": error_like_rate_percent,
                "unique_users": unique_users,
                "avg_latency_ms": avg_latency_ms,
                "p95_latency_ms": p95_latency_ms,
                "out_of_hours_events": out_of_hours_events,
            },
            "policy_decisions": {
                "allowed": allowed_events,
                "blocked": blocked_events,
                "top_block_reasons": top_block_reasons,
            },
            "usage": {
                "top_domains": top_domains,
                "top_active_users": top_active_users,
            },
            "anomalies": anomalies[:anomaly_limit],
        }

    @staticmethod
    def _is_error_like(row: AuditLog) -> bool:
        latency_flag = (row.latency_flag or "").strip().lower()
        block_reason = (row.block_reason or "").strip().lower()
        return latency_flag in ERROR_LATENCY_FLAGS or block_reason in {
            "system_error",
            "connector_error",
            "internal_error",
            "execution_error",
            "source_error",
        }

    @staticmethod
    def _ensure_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

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


audit_dashboard_service = AuditDashboardService()
