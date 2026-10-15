"""
Atualização de schema leve e idempotente.

`Base.metadata.create_all` cria tabelas novas, mas NÃO adiciona colunas a tabelas
já existentes. Enquanto o projeto não adota Alembic, este módulo garante que
bancos criados por versões anteriores recebam as colunas novas.
Compatível com SQLite e PostgreSQL.
"""
import logging
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

logger = logging.getLogger(__name__)

# tabela -> {coluna: DDL do tipo}
ADDED_COLUMNS = {
    "sources": {
        "etag": "VARCHAR(255)",
        "last_modified": "VARCHAR(100)",
        "last_status_code": "INTEGER",
        "last_error": "TEXT",
        "last_success_at": "TIMESTAMP",
        "last_items_found": "INTEGER DEFAULT 0",
        "next_check_at": "TIMESTAMP",
        "publisher": "VARCHAR(100)",
    },
}

ADDED_INDEXES = [
    ("ix_sources_next_check_at", "sources", "next_check_at"),
]


def upgrade_schema(conn: Connection) -> None:
    """Adiciona colunas/índices ausentes. Seguro para rodar a cada inicialização."""
    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())

    for table, columns in ADDED_COLUMNS.items():
        if table not in existing_tables:
            continue  # create_all criará a tabela completa
        existing_cols = {c["name"] for c in inspector.get_columns(table)}
        for col, ddl in columns.items():
            if col not in existing_cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}"))
                logger.info("[Schema] Coluna adicionada: %s.%s", table, col)

    for index_name, table, column in ADDED_INDEXES:
        if table in existing_tables:
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {index_name} ON {table} ({column})"))
