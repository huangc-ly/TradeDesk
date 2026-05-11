import duckdb
from contextlib import contextmanager
from .config import settings


class Database:
    """DuckDB connection manager for querying parquet files."""

    def __init__(self) -> None:
        self._conn: duckdb.DuckDBPyConnection | None = None

    def connect(self) -> duckdb.DuckDBPyConnection:
        """Get or create the DuckDB connection."""
        if self._conn is None:
            self._conn = duckdb.connect(settings.duckdb_database)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            return self.connect()
        return self._conn


db = Database()
