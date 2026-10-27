"""Shared helpers for running SQL on poc-warehouse through the Statement Execution API.

Authentication comes from a Databricks CLI profile in ~/.databrickscfg (OAuth U2M),
so the statement runs as the user that profile signed in as.
"""

import os
import shutil
import time

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import Disposition, StatementState

WAREHOUSE_NAME = "poc-warehouse"


def client(profile: str) -> WorkspaceClient:
    # The SDK's own CLI lookup resolves symlinks, which breaks shim installs (mise, asdf)
    # by calling the shim manager instead of the CLI. Pointing it at PATH's entry avoids that.
    if "DATABRICKS_CLI_PATH" not in os.environ and (cli := shutil.which("databricks")):
        os.environ["DATABRICKS_CLI_PATH"] = cli
    return WorkspaceClient(profile=profile)


def warehouse_id(w: WorkspaceClient, name: str = WAREHOUSE_NAME) -> str:
    for wh in w.warehouses.list():
        if wh.name == name:
            return wh.id
    raise SystemExit(f"No SQL warehouse named {name!r} is visible to this profile.")


def split_statements(sql: str) -> list[str]:
    """Split a SQL script on semicolons that sit outside quotes and comments."""
    statements, buf = [], []
    i, n = 0, len(sql)
    quote = None
    while i < n:
        ch = sql[i]
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
        elif ch in ("'", '"', "`"):
            quote = ch
            buf.append(ch)
        elif sql.startswith("--", i):
            end = sql.find("\n", i)
            i = n if end == -1 else end
            continue
        elif ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def run(w: WorkspaceClient, wid: str, statement: str) -> tuple[list[str], list[list]]:
    """Execute one statement and return (column names, rows)."""
    resp = w.statement_execution.execute_statement(
        warehouse_id=wid,
        statement=statement,
        wait_timeout="50s",
        disposition=Disposition.INLINE,
    )
    while resp.status.state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(2)
        resp = w.statement_execution.get_statement(resp.statement_id)
    if resp.status.state != StatementState.SUCCEEDED:
        err = resp.status.error
        msg = err.message if err else resp.status.state.value
        raise RuntimeError(f"{msg}\n--- statement ---\n{statement}")
    cols = [c.name for c in resp.manifest.schema.columns] if resp.manifest and resp.manifest.schema.columns else []
    rows = resp.result.data_array if resp.result and resp.result.data_array else []
    return cols, rows
