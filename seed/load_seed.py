# /// script
# requires-python = ">=3.11"
# dependencies = ["databricks-sdk>=0.60"]
# ///
"""Load seed/*.csv into the poc tables through the SQL Statement Execution API.

    uv run seed/load_seed.py            # uses the admin profile

Idempotent: each table is truncated, then reloaded with one INSERT.
Once the row filters in sql/03_row_filters.sql are on, admin counts 0 rows in the
three filtered tables. Count them as carol (finance_analysts sees every row):

    uv run tools/run_sql.py --profile carol -e "SELECT count(*) FROM poc.sales.orders"
"""

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import dbsql  # noqa: E402

# table, csv file, columns, and the SQL type each column is cast to
TABLES = [
    ("poc.sales.customer_accounts", "accounts.csv", {
        "account_id": "STRING", "account_name": "STRING", "region": "STRING",
        "owner_email": "STRING", "contact_name": "STRING", "contact_email": "STRING",
        "contact_phone": "STRING", "annual_revenue": "DECIMAL(18,2)", "status": "STRING"}),
    ("poc.sales.orders", "orders.csv", {
        "order_id": "STRING", "account_id": "STRING", "order_date": "DATE",
        "amount": "DECIMAL(18,2)"}),
    ("poc.support.tickets", "tickets.csv", {
        "ticket_id": "STRING", "account_id": "STRING", "opened_date": "DATE",
        "severity": "STRING", "status": "STRING", "reporter_email": "STRING",
        "summary": "STRING"}),
    # Unfiltered ownership lookup read by the row filter and mask functions.
    ("poc.governance.account_owners", "accounts.csv", {
        "account_id": "STRING", "owner_email": "STRING"}),
]


def literal(value: str, sql_type: str) -> str:
    if value == "":
        return "NULL"
    quoted = "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
    if sql_type == "STRING":
        return quoted
    return f"CAST({quoted} AS {sql_type})"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile", default="admin")
    args = ap.parse_args()

    w = dbsql.client(args.profile)
    wid = dbsql.warehouse_id(w)

    for table, filename, columns in TABLES:
        with (ROOT / "seed" / filename).open() as f:
            rows = list(csv.DictReader(f))
        values = ",\n".join(
            "(" + ", ".join(literal(r[c], t) for c, t in columns.items()) + ")" for r in rows
        )
        dbsql.run(w, wid, f"TRUNCATE TABLE {table}")
        dbsql.run(w, wid, f"INSERT INTO {table} ({', '.join(columns)}) VALUES\n{values}")
        _, result = dbsql.run(w, wid, f"SELECT count(*) FROM {table}")
        print(f"{table}: {result[0][0]} rows visible to {args.profile}")


if __name__ == "__main__":
    main()
