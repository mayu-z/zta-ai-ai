from __future__ import annotations

from urllib.parse import urlparse


def _parse_allowlist(raw_allowlist: str) -> list[str]:
    return [entry.strip().lower() for entry in raw_allowlist.split(",") if entry.strip()]


def _host_allowed(host: str, allowlist: list[str]) -> bool:
    for pattern in allowlist:
        if pattern.startswith("*."):
            suffix = pattern[2:]
            if host == suffix or host.endswith(f".{suffix}"):
                return True
        elif host == pattern:
            return True
    return False


def enforce_egress_url_allowed(target_url: str, raw_allowlist: str) -> None:
    allowlist = _parse_allowlist(raw_allowlist)
    if not allowlist:
        return

    parsed = urlparse(target_url)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise RuntimeError("Egress target URL must include a valid host")

    if not _host_allowed(host, allowlist):
        raise RuntimeError(
            f"Egress host '{host}' is not in EGRESS_ALLOWED_HOSTS"
        )
