from __future__ import annotations

LOCAL_STORE_SOURCE_TYPES = {"ipeds_claims", "mock_claims"}
SQL_CONNECTOR_TYPES = {"mysql", "postgresql"}


def is_local_store_source_type(source_type: str) -> bool:
    return source_type.strip().lower() in LOCAL_STORE_SOURCE_TYPES
