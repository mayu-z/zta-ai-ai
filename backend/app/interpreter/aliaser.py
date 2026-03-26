from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FieldVisibility, SchemaField


def apply_schema_aliasing(db: Session, tenant_id: str, prompt: str) -> tuple[str, list[str]]:
    schema_rows = db.scalars(
        select(SchemaField).where(
            SchemaField.tenant_id == tenant_id,
            SchemaField.visibility != FieldVisibility.hidden,
        )
    ).all()

    aliased_prompt = prompt
    real_identifiers: list[str] = []

    for row in schema_rows:
        for real_name in {row.real_table, row.real_column}:
            if not real_name:
                continue
            pattern = re.compile(rf"\b{re.escape(real_name)}\b", flags=re.IGNORECASE)
            if pattern.search(aliased_prompt):
                aliased_prompt = pattern.sub(row.alias_token, aliased_prompt)
                real_identifiers.append(real_name.lower())

    return aliased_prompt, sorted(set(real_identifiers))
