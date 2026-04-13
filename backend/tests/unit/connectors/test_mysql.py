from __future__ import annotations

from uuid import uuid4

from app.agentic.connectors.mysql import MariaDBConnector, MySQLConnector


def test_mariadb_alias_points_to_mysql_connector() -> None:
    assert MariaDBConnector is MySQLConnector


def test_mysql_connection_url_translation(monkeypatch) -> None:
    connector = MySQLConnector(tenant_id=uuid4(), config={"connection_url": "mysql://u:p@localhost/db"})

    monkeypatch.setattr(
        "app.agentic.connectors.mysql.secret_manager.get_secret",
        lambda key, fallback="": fallback,
    )

    resolved = connector._resolve_connection_url()
    assert resolved.startswith("mysql+aiomysql://")


def test_mariadb_connection_url_translation(monkeypatch) -> None:
    connector = MySQLConnector(
        tenant_id=uuid4(),
        config={"connection_url": "mariadb://u:p@localhost/db", "source_dialect": "mariadb"},
    )

    monkeypatch.setattr(
        "app.agentic.connectors.mysql.secret_manager.get_secret",
        lambda key, fallback="": fallback,
    )

    resolved = connector._resolve_connection_url()
    assert resolved.startswith("mysql+aiomysql://")
