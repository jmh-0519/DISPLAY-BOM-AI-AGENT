from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager

from database import SQLiteDatabase


class SQLiteUnitOfWork(AbstractContextManager):
    """하나의 SQLite Connection으로 Production 변경을 원자적으로 처리합니다."""

    def __init__(self, database: SQLiteDatabase) -> None:
        self.database = database
        self.connection: sqlite3.Connection | None = None

    def __enter__(self) -> "SQLiteUnitOfWork":
        self.connection = self.database.connect()
        self.connection.execute("BEGIN IMMEDIATE")
        return self

    def commit(self) -> None:
        if self.connection is None:
            raise RuntimeError("UnitOfWork가 시작되지 않았습니다.")
        self.connection.commit()

    def rollback(self) -> None:
        if self.connection is not None:
            self.connection.rollback()

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
        finally:
            if self.connection is not None:
                self.connection.close()
                self.connection = None
        return False
