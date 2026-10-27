# /// script
# requires-python = ">=3.11"
# dependencies = ["databricks-sdk>=0.60"]
# ///
"""Run SQL files or an inline statement on poc-warehouse as a CLI profile.

    uv run tools/run_sql.py --profile admin sql/01_schema.sql
    uv run tools/run_sql.py --profile alice -e "SELECT current_user()"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbsql  # noqa: E402


def print_table(cols: list[str], rows: list[list]) -> None:
    if not cols:
        return
    cells = [[("NULL" if v is None else str(v)) for v in row] for row in rows]
    widths = [max([len(c)] + [len(r[i]) for r in cells]) for i, c in enumerate(cols)]
    print("  ".join(c.ljust(widths[i]) for i, c in enumerate(cols)))
    print("  ".join("-" * wd for wd in widths))
    for r in cells:
        print("  ".join(v.ljust(widths[i]) for i, v in enumerate(r)))
    print(f"({len(rows)} rows)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", required=True, help="Databricks CLI profile (admin, alice, bob, carol)")
    ap.add_argument("--warehouse", default=dbsql.WAREHOUSE_NAME)
    ap.add_argument("-e", "--execute", action="append", help="inline SQL to run instead of files (repeatable)")
    ap.add_argument("-q", "--quiet", action="store_true", help="print only result sets, not each statement")
    ap.add_argument("files", nargs="*", type=Path)
    args = ap.parse_args()

    if not args.execute and not args.files:
        ap.error("pass SQL files or -e")

    w = dbsql.client(args.profile)
    wid = dbsql.warehouse_id(w, args.warehouse)
    scripts = args.execute if args.execute else [f.read_text() for f in args.files]

    for script in scripts:
        for stmt in dbsql.split_statements(script):
            if not args.quiet:
                print(f"\n>>> {stmt.splitlines()[0][:100]}")
            try:
                cols, rows = dbsql.run(w, wid, stmt)
            except RuntimeError as err:
                sys.exit(f"ERROR: {err}")
            print_table(cols, rows)


if __name__ == "__main__":
    main()
