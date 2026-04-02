from __future__ import annotations

import re

from app.core.exceptions import AuthorizationError

# Explicit domain keywords - these definitively identify a domain
DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "academic": (
        "attendance",
        "grade",
        "gpa",
        "subject",
        "course",
        "timetable",
        "semester",
        "exam",
        "result",
        "class",
    ),
    "finance": (
        "finance",
        "fee",
        "payment",
        "budget",
        "revenue",
        "p&l",
        "salary",
        "payroll",
        "invoice",
        "financial",
    ),
    "hr": ("leave", "faculty record", "employee", "payslip", "attrition"),
    "admissions": (
        "admission",
        "admissions",
        "applicant",
        "applicants",
        "open admission",
    ),
    "department": ("department", "dept", "faculty performance"),
    "campus": (
        "cross campus",
        "campus aggregate",
        "enrollment",
        "enrolment",
        "enrolled",
        "headcount",
        "institution",
        "hbcu",
        "sector",
        "public",
        "private",
        "demographics",
        "size distribution",
        "size",
        "students",
    ),
    "admin": (
        "audit",
        "audit log",
        "audit-log",
        "schema",
        "connector",
        "connectors",
        "kill switch",
        "data sources",
        "data-sources",
        "admin dashboard",
    ),
}

# Modifier keywords - only trigger campus domain when no explicit domain is found
AGGREGATION_MODIFIERS: tuple[str, ...] = (
    "kpi",
    "aggregate",
    "summary",
    "trend",
    "overview",
    "metrics",
)


def normalize_domain(domain: str) -> str:
    """Extract base domain from suffixed domain like 'finance_aggregate' -> 'finance'."""
    if "_" in domain:
        return domain.split("_", 1)[0]
    return domain


def detect_domains(prompt: str) -> list[str]:
    lower_prompt = prompt.lower()
    detected: list[str] = []

    # First pass: detect explicit domain keywords
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for keyword in keywords:
            if re.search(rf"\b{re.escape(keyword)}\b", lower_prompt):
                detected.append(domain)
                break

    # Second pass: if no explicit domain found but aggregation modifiers present, default to campus
    if not detected:
        has_aggregation_modifier = any(
            re.search(rf"\b{re.escape(mod)}\b", lower_prompt)
            for mod in AGGREGATION_MODIFIERS
        )
        if has_aggregation_modifier:
            detected = ["campus"]
        else:
            detected = ["academic"]

    return sorted(set(detected))


def is_domain_allowed(domain: str, allowed_domains: list[str]) -> bool:
    """
    Check if a detected domain is allowed by the user's allowed_domains list.
    
    For aggregate domains (e.g., finance_aggregate):
    - Allows 'campus' domain (IPEDS aggregate data)
    - Does NOT allow the base domain (e.g., finance) for transactional data
    
    This ensures executives can query aggregate institution data but not 
    transactional financial records.
    """
    # Sensitive domains that should NOT be accessible via aggregate permissions
    # E.g., finance_aggregate allows campus IPEDS data, NOT transactional finance
    SENSITIVE_DOMAINS = {"finance", "hr"}
    
    for allowed in allowed_domains:
        # Exact match always works
        if allowed == domain:
            return True
        
        # For aggregate permissions, check what they allow
        if allowed.endswith("_aggregate"):
            base_domain = normalize_domain(allowed)
            
            # Aggregate permissions always allow 'campus' domain (IPEDS data)
            if domain == "campus":
                return True
            
            # For sensitive domains, aggregate permission does NOT grant base domain access
            # E.g., finance_aggregate does NOT allow 'finance' domain
            if base_domain in SENSITIVE_DOMAINS:
                continue
            
            # For non-sensitive domains (academic, etc.), aggregate allows base domain
            # but policy layer enforces aggregate-only output
            if domain == base_domain:
                return True
        else:
            # Non-aggregate permission - use normalized matching
            if normalize_domain(allowed) == domain:
                return True
    
    return False


def enforce_domain_gate(
    detected_domains: list[str], allowed_domains: list[str]
) -> None:
    blocked = [
        domain
        for domain in detected_domains
        if not is_domain_allowed(domain, allowed_domains)
    ]
    if blocked:
        raise AuthorizationError(
            message=f"Domain gate blocked out-of-scope domains: {', '.join(blocked)}",
            code="DOMAIN_FORBIDDEN",
        )
