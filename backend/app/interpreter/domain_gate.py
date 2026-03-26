from __future__ import annotations

import re

from app.core.exceptions import AuthorizationError


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
    "finance": ("fee", "payment", "budget", "revenue", "p&l", "salary", "payroll", "invoice"),
    "hr": ("leave", "faculty record", "employee", "payslip", "attrition"),
    "admissions": ("admission", "applicant", "enrolment", "enrollment"),
    "department": ("department", "dept", "faculty performance"),
    "campus": ("kpi", "cross campus", "aggregate", "summary", "trend"),
    "admin": ("audit", "schema", "connector", "kill switch"),
}


def normalize_domain(domain: str) -> str:
    if "_" in domain:
        return domain.split("_", 1)[0]
    return domain


def detect_domains(prompt: str) -> list[str]:
    lower_prompt = prompt.lower()
    detected: list[str] = []
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for keyword in keywords:
            if re.search(rf"\b{re.escape(keyword)}\b", lower_prompt):
                detected.append(domain)
                break

    if not detected:
        detected = ["academic"]
    return sorted(set(detected))


def is_domain_allowed(domain: str, allowed_domains: list[str]) -> bool:
    canonical = normalize_domain(domain)
    return any(normalize_domain(allowed) == canonical for allowed in allowed_domains)


def enforce_domain_gate(detected_domains: list[str], allowed_domains: list[str]) -> None:
    blocked = [domain for domain in detected_domains if not is_domain_allowed(domain, allowed_domains)]
    if blocked:
        raise AuthorizationError(
            message=f"Domain gate blocked out-of-scope domains: {', '.join(blocked)}",
            code="DOMAIN_FORBIDDEN",
        )
