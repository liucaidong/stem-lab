"""Minimal psycopg adapter for the atomic v2alpha2 PostgreSQL entry points."""
from __future__ import annotations
import re
from typing import Any, Callable, Mapping
from psycopg import sql
from psycopg.types.json import Jsonb

class PostgresWorkerStore:
    """One SECURITY DEFINER entry point per command; the database owns the UOW."""
    def __init__(self, connection_factory: Callable[[], Any], schema: str) -> None:
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", schema):
            raise ValueError("schema must be a simple PostgreSQL identifier")
        self._connection_factory = connection_factory
        self._schema = schema

    def _call(self, function_name: str, payload_b64url: str, signature_b64url: str,
              operation_arguments: Mapping[str, object]) -> dict[str, object]:
        if function_name not in {"apply_job_complete_v2alpha2","reconcile_request_receipt_v2alpha2"}:
            raise ValueError("unsupported v2alpha2 database entry point")
        conn = self._connection_factory()
        try:
            statement = sql.SQL("SELECT {}.{}(%s,%s,%s)").format(
                sql.Identifier(self._schema), sql.Identifier(function_name))
            with conn.transaction():
                row = conn.execute(statement,(payload_b64url,signature_b64url,
                                               Jsonb(dict(operation_arguments)))).fetchone()
            if row is None or not isinstance(row[0],dict):
                raise RuntimeError("v2alpha2 database entry point returned no JSON object")
            return row[0]
        finally:
            conn.close()

    def apply_job_complete(self,payload_b64url: str,signature_b64url: str,
                           operation_arguments: Mapping[str,object])->dict[str,object]:
        return self._call("apply_job_complete_v2alpha2",payload_b64url,
                          signature_b64url,operation_arguments)

    def reconcile_request_receipt(self,payload_b64url: str,signature_b64url: str,
                                  operation_arguments: Mapping[str,object])->dict[str,object]:
        return self._call("reconcile_request_receipt_v2alpha2",payload_b64url,
                          signature_b64url,operation_arguments)
