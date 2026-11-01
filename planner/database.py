"""Small DB-API adapter: local SQLite and durable hosted PostgreSQL.

The application uses a fixed set of parameterized SQL statements. PostgreSQL
translation is limited to that dialect; it is not a general-purpose SQL parser.
"""

import re
import sqlite3


class Row(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)


class Cursor:
    def __init__(self, cursor, inserted=False):
        self.cursor = cursor
        self.rowcount = cursor.rowcount
        self.lastrowid = cursor.fetchone()[0] if inserted else None

    def convert(self, row):
        if row is None:
            return None
        return Row(zip([column.name for column in self.cursor.description], row))

    def fetchone(self):
        return self.convert(self.cursor.fetchone())

    def __iter__(self):
        return (self.convert(row) for row in self.cursor)


def postgres_schema(schema):
    schema = re.sub(r"INTEGER PRIMARY KEY(?: AUTOINCREMENT)?", "SERIAL PRIMARY KEY", schema)
    schema = re.sub(r"\bREAL\b", "DOUBLE PRECISION", schema)
    return re.sub(r"\bend\b", '"end"', schema)


class PostgresConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, query, params=()):
        import psycopg

        if query.strip() in {"BEGIN IMMEDIATE", "BEGIN"}:
            # Connection context owns the transaction. Write contexts take the
            # shared advisory lock before any snapshot or mutation.
            query = "SELECT 1"
        query = query.replace("?", "%s")
        query = re.sub(r"\bend\b", '"end"', query)
        inserted = bool(re.match(r"\s*INSERT INTO (subjects|topics|cards|sessions|assessments|review_logs|documents)\b", query, re.I))
        if inserted:
            query = query.rstrip("; ") + " RETURNING id"
        try:
            return Cursor(self.connection.execute(query, params), inserted)
        except psycopg.IntegrityError as exc:
            raise sqlite3.IntegrityError("Record violates a database constraint.") from exc

    def executescript(self, schema):
        for statement in postgres_schema(schema).split(";"):
            if statement.strip():
                self.connection.execute(statement)
