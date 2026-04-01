from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ConversationalResponse:
    is_conversational: bool
    response: str | None = None


# Patterns allow repeated trailing characters (e.g., "heyy", "helloo", "hiii")
GREETING_PATTERNS: tuple[str, ...] = (
    r"^h+i+[\s!.,?]*$",  # hi, hii, hiii, etc.
    r"^h+e+y+[\s!.,?]*$",  # hey, heyy, heyyy, etc.
    r"^h+e+l+o+[\s!.,?]*$",  # helo, heloo, etc.
    r"^h+e+l+l+o+[\s!.,?]*$",  # hello, helloo, hellooo, etc.
    r"^greetings[\s!.,?]*$",
    r"^good\s*(morning|afternoon|evening|day)[\s!.,?]*$",
    r"^howdy[\s!.,?]*$",
    r"^sup+[\s!.,?]*$",  # sup, supp, suppp
    r"^what'?s\s*up+[\s!.,?]*$",
    r"^yo+[\s!.,?]*$",  # yo, yoo, yooo
)

HELP_PATTERNS: tuple[str, ...] = (
    r"^help+[\s!.,?]*$",
    r"^what can you do[\s!.,?]*$",
    r"^what do you do[\s!.,?]*$",
    r"^how can you help[\s!.,?]*$",
    r"^what are you[\s!.,?]*$",
    r"^who are you[\s!.,?]*$",
    r"^tell me about yourself[\s!.,?]*$",
)

THANKS_PATTERNS: tuple[str, ...] = (
    r"^thanks+[\s!.,?]*$",
    r"^thank you+[\s!.,?]*$",
    r"^thx+[\s!.,?]*$",
    r"^ty+[\s!.,?]*$",
    r"^appreciate it[\s!.,?]*$",
)

FAREWELL_PATTERNS: tuple[str, ...] = (
    r"^bye+[\s!.,?]*$",
    r"^goodbye+[\s!.,?]*$",
    r"^see you[\s!.,?]*$",
    r"^later[\s!.,?]*$",
    r"^take care[\s!.,?]*$",
)

HOW_ARE_YOU_PATTERNS: tuple[str, ...] = (
    r"^how\s*(are|r)\s*(you|u)[\s!.,?]*$",
    r"^how'?s\s*it\s*going[\s!.,?]*$",
)

GREETING_RESPONSES: list[str] = [
    "Hello! I'm your data assistant. I can help you with information about attendance, grades, fees, courses, and more. What would you like to know?",
]

HELP_RESPONSES: list[str] = [
    "I can help you access information based on your role. You can ask me about:\n"
    "- Attendance records\n"
    "- Grade summaries and GPA\n"
    "- Fee balances and payments\n"
    "- Course information\n"
    "- Department metrics\n\n"
    "Just ask your question naturally, and I'll do my best to help!",
]

THANKS_RESPONSES: list[str] = [
    "You're welcome! Let me know if you need anything else.",
]

FAREWELL_RESPONSES: list[str] = [
    "Goodbye! Have a great day!",
]

HOW_ARE_YOU_RESPONSES: list[str] = [
    "I'm doing great, thank you for asking! How can I assist you today?",
]


def detect_conversational_query(query: str) -> ConversationalResponse:
    """
    Detect if a query is conversational (greetings, help requests, etc.)
    rather than a data query.

    Returns a ConversationalResponse with is_conversational=True and a response
    if it's a conversational query, otherwise is_conversational=False.
    """
    normalized = query.strip().lower()

    # Check greetings
    for pattern in GREETING_PATTERNS:
        if re.match(pattern, normalized, re.IGNORECASE):
            return ConversationalResponse(
                is_conversational=True,
                response=GREETING_RESPONSES[0],
            )

    # Check how are you
    for pattern in HOW_ARE_YOU_PATTERNS:
        if re.match(pattern, normalized, re.IGNORECASE):
            return ConversationalResponse(
                is_conversational=True,
                response=HOW_ARE_YOU_RESPONSES[0],
            )

    # Check help requests
    for pattern in HELP_PATTERNS:
        if re.match(pattern, normalized, re.IGNORECASE):
            return ConversationalResponse(
                is_conversational=True,
                response=HELP_RESPONSES[0],
            )

    # Check thanks
    for pattern in THANKS_PATTERNS:
        if re.match(pattern, normalized, re.IGNORECASE):
            return ConversationalResponse(
                is_conversational=True,
                response=THANKS_RESPONSES[0],
            )

    # Check farewells
    for pattern in FAREWELL_PATTERNS:
        if re.match(pattern, normalized, re.IGNORECASE):
            return ConversationalResponse(
                is_conversational=True,
                response=FAREWELL_RESPONSES[0],
            )

    return ConversationalResponse(is_conversational=False)


# Keywords that indicate a data-related query
DATA_KEYWORDS: tuple[str, ...] = (
    # Academic
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
    "marks",
    "score",
    # Finance
    "fee",
    "payment",
    "budget",
    "revenue",
    "salary",
    "payroll",
    "invoice",
    "balance",
    "due",
    "paid",
    # HR
    "leave",
    "faculty",
    "employee",
    "payslip",
    "attrition",
    "staff",
    # Admissions
    "admission",
    "applicant",
    "enrolment",
    "enrollment",
    "application",
    # Department
    "department",
    "dept",
    "performance",
    # Campus/Executive
    "kpi",
    "campus",
    "aggregate",
    "summary",
    "trend",
    "metric",
    "total",
    "count",
    "average",
    "report",
    "overview",
    # IPEDS/Institution data
    "institution",
    "hbcu",
    "public",
    "private",
    "demographics",
    "size",
    "distribution",
    "sector",
    "college",
    "university",
    # Admin
    "audit",
    "schema",
    "connector",
    # General data queries
    "show",
    "tell",
    "what is",
    "what's",
    "how many",
    "how much",
    "give me",
    "get",
    "list",
    "display",
    "my",
)

UNCLEAR_RESPONSE = (
    "I'm not sure what you're looking for. I can help you with information about:\n"
    "- Attendance records\n"
    "- Grades and GPA\n"
    "- Fee balances\n"
    "- Course information\n"
    "- Department metrics\n\n"
    "Could you please rephrase your question?"
)


def is_unclear_query(query: str) -> ConversationalResponse:
    """
    Detect if a query is unclear and doesn't appear to be a data request.

    Returns a ConversationalResponse with is_conversational=True if the query
    doesn't contain any data-related keywords and should get a clarification response.
    """
    normalized = query.strip().lower()

    # If query is very short (1-2 words) and doesn't match data keywords, it's unclear
    words = normalized.split()

    # Check if any data keyword is present
    has_data_keyword = any(keyword in normalized for keyword in DATA_KEYWORDS)

    if has_data_keyword:
        return ConversationalResponse(is_conversational=False)

    # Short queries without data keywords are unclear
    if len(words) <= 3:
        return ConversationalResponse(
            is_conversational=True,
            response=UNCLEAR_RESPONSE,
        )

    # Longer queries without any data keywords are also unclear
    if not has_data_keyword:
        return ConversationalResponse(
            is_conversational=True,
            response=UNCLEAR_RESPONSE,
        )

    return ConversationalResponse(is_conversational=False)
