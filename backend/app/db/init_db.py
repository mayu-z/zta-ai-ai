from app.db.models import Base
from app.db.session import engine

# Register agentic ORM models on shared metadata before create_all.
from app.agentic import db_models as _agentic_db_models  # noqa: F401


def create_all_tables() -> None:
    Base.metadata.create_all(bind=engine)
