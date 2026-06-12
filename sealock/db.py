"""Thin MariaDB/MySQL access layer built on PyMySQL.

Holds at most one live connection. Credentials live only in memory for the
duration of the session and are never written to disk by this module.
"""
from __future__ import annotations

import pymysql
from pymysql.cursors import DictCursor


class DatabaseError(Exception):
    """Raised for connection / query failures, with a human-friendly message."""


def _friendly(exc: Exception) -> str:
    """Turn a raw driver exception into something readable in the UI."""
    if isinstance(exc, pymysql.err.OperationalError):
        code = exc.args[0] if exc.args else None
        msg = exc.args[1] if len(exc.args) > 1 else str(exc)
        hints = {
            1045: "접속 권한이 거부되었습니다. 사용자/비밀번호를 확인하세요.",
            1049: "해당 데이터베이스(스키마)가 존재하지 않습니다.",
            2003: "서버에 연결할 수 없습니다. 호스트/포트와 방화벽을 확인하세요.",
            2005: "호스트 이름을 확인할 수 없습니다.",
        }
        return hints.get(code, f"{msg} (code {code})")
    return str(exc)


class Database:
    def __init__(self) -> None:
        self.conn: pymysql.connections.Connection | None = None
        self.info: dict = {}

    # ── connection lifecycle ────────────────────────────────────────────
    def _open(self, host, port, user, password, database, timeout=6):
        return pymysql.connect(
            host=host,
            port=int(port or 3306),
            user=user,
            password=password or "",
            database=database,
            charset="utf8mb4",
            cursorclass=DictCursor,
            connect_timeout=timeout,
            read_timeout=30,
            autocommit=True,
        )

    def test(self, host, port, user, password, database) -> str:
        """Open a throwaway connection and return the server version string."""
        try:
            conn = self._open(host, port, user, password, database)
        except Exception as exc:  # noqa: BLE001
            raise DatabaseError(_friendly(exc)) from exc
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT VERSION() AS v")
                row = cur.fetchone() or {}
            return str(row.get("v", "unknown"))
        finally:
            conn.close()

    def connect(self, host, port, user, password, database) -> None:
        """Establish the persistent session connection."""
        self.close()
        try:
            self.conn = self._open(host, port, user, password, database)
        except Exception as exc:  # noqa: BLE001
            raise DatabaseError(_friendly(exc)) from exc
        self.info = {
            "host": host,
            "port": int(port or 3306),
            "user": user,
            "database": database,
        }

    @property
    def database(self) -> str | None:
        return self.info.get("database")

    def is_connected(self) -> bool:
        return self.conn is not None

    # ── queries ─────────────────────────────────────────────────────────
    def query(self, sql: str, params=None) -> list[dict]:
        if not self.conn:
            raise DatabaseError("데이터베이스에 연결되어 있지 않습니다.")
        try:
            self.conn.ping(reconnect=True)
            with self.conn.cursor() as cur:
                cur.execute(sql, params or ())
                return list(cur.fetchall())
        except Exception as exc:  # noqa: BLE001
            raise DatabaseError(_friendly(exc)) from exc

    def query_one(self, sql: str, params=None) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def close(self) -> None:
        if self.conn:
            try:
                self.conn.close()
            except Exception:  # noqa: BLE001
                pass
            self.conn = None
