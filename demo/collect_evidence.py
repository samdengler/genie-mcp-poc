# /// script
# requires-python = ">=3.11"
# dependencies = ["databricks-sdk>=0.60"]
# ///
"""Build the demo evidence files in demo/evidence/.

    uv run demo/collect_evidence.py                          # since yesterday, as admin
    uv run demo/collect_evidence.py --since 2026-10-24T03:07   # UTC; just the demo run

Writes:
  generated_sql.md   the SQL Genie ran for the demo users, with a check that none
                     of it carries ownership or masking logic
  gateway_usage.csv  system.ai_gateway.usage rows for their Genie One tool calls
  audit.csv          system.access.audit rows for Genie and MCP calls by the same users
  query_history.csv  Genie's statements for the same users, from the Query History API

The SQL comes from the Query History API. system.query.history ran more than two days
behind on this trial workspace, and Genie One leaves query_items empty when it hands a
question to a Genie space, so the client's JSON files miss that SQL. The gateway and
audit tables lag by 20 to 30 minutes, so run this a while after the demo.
"""

import argparse
import csv
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from databricks.sdk.service import sql

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import dbsql  # noqa: E402

EVIDENCE = ROOT / "demo" / "evidence"
USERS = ("alice@example.com", "bob@example.com", "carol@example.com", "david@example.com")
# Service names seen in this workspace's audit log for Genie and managed MCP traffic.
SERVICES = ("managedMcp", "mcpService", "aibiGenie", "genieChat")
# Anything here in Genie's SQL would mean the governance lives in the query, not in Unity Catalog.
GOVERNANCE_TOKENS = ("owner_email", "current_user", "is_account_group_member", "is_member", "case when", "***")


def governance_in(sql: str) -> list[str]:
    return [t for t in GOVERNANCE_TOKENS if t in sql.lower()]


def genie_statements(w, since: datetime) -> list[dict]:
    """Genie's SELECT statements run as a demo user since a UTC time."""
    start_ms = int(since.replace(tzinfo=timezone.utc).timestamp() * 1000)
    kwargs = {"filter_by": sql.QueryFilter(query_start_time_range=sql.TimeRange(start_time_ms=start_ms))}
    out = []
    while True:
        page = w.query_history.list(max_results=1000, **kwargs)
        for q in page.res or []:
            if (q.user_name in USERS and q.statement_type and q.statement_type.value == "SELECT"
                    and "genie" in (q.client_application or "").lower()):
                out.append({
                    "start_time": datetime.fromtimestamp(q.query_start_time_ms / 1000, timezone.utc)
                                          .strftime("%Y-%m-%d %H:%M:%S"),
                    "user_name": q.user_name, "client_application": q.client_application,
                    "genie_space_id": q.query_source.genie_space_id if q.query_source else None,
                    "status": q.status.value if q.status else None, "rows_produced": q.rows_produced,
                    "query_text": q.query_text})
        if not page.has_next_page:
            return sorted(out, key=lambda r: r["start_time"])
        # A page token replaces the filter on later pages.
        kwargs = {"page_token": page.next_page_token}


def write_generated_sql(statements: list[dict]) -> None:
    runs = [json.loads(p.read_text()) | {"file": p.name} for p in sorted(EVIDENCE.glob("*.json"))]
    lines = [
        "# Generated SQL",
        "",
        "The SQL Genie ran for each client run in this folder, taken from the MCP tool results",
        "(`demo/evidence/*.json`, written by `client/genie_client.py --json`). The last column",
        "checks each statement for ownership or masking logic: " + ", ".join(f"`{t}`" for t in GOVERNANCE_TOKENS) + ".",
        "",
        "| Run | User | Server | Question | Rows | Ownership or masking logic |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in runs:
        found = sorted({t for q in r["queries"] for t in governance_in(q["sql"] or "")})
        rows = ", ".join(str(len(q["rows"])) for q in r["queries"]) or "0"
        lines.append(f"| `{r['file']}` | {r['user']} | {r['server']} | {r['question']} | {rows} | "
                     f"{'FOUND: ' + ', '.join(found) if found else 'none'} |")
    lines += [
        "",
        "## Genie's statements from the Query History API",
        "",
        "Every SELECT Genie ran as a demo user in the window, including the runs from",
        "Claude and the Genie One runs that the client's JSON files have no SQL for.",
        "",
        "| Time (UTC) | User | Client application | Genie space | Rows | Ownership or masking logic |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for q in statements:
        found = governance_in(q["query_text"] or "")
        lines.append(f"| {q['start_time']} | {q['user_name']} | {q['client_application']} | "
                     f"{q['genie_space_id'] or 'none'} | {q['rows_produced']} | "
                     f"{'FOUND: ' + ', '.join(found) if found else 'none'} |")
    for q in statements:
        lines += ["", f"{q['start_time']}, {q['user_name']}, {q['client_application']}:", "",
                  "```sql", (q["query_text"] or "").strip(), "```"]
    for r in runs:
        lines += ["", f"## {r['user']}, {r['server']}: {r['question']}", "",
                  f"Asked {r['asked_at']}. File `{r['file']}`. Genie conversation: {r.get('deep_link')}", ""]
        for i, q in enumerate(r["queries"], 1):
            lines += [f"Query {i} ({len(q['rows'])} rows, columns: {', '.join(q['columns']) or 'none'}):", "",
                      "```sql", (q["sql"] or "").strip(), "```", ""]
    (EVIDENCE / "generated_sql.md").write_text("\n".join(lines).rstrip() + "\n")
    print(f"generated_sql.md: {len(runs)} client runs, {len(statements)} statements from query history")


def write_csv(name: str, cols: list[str], rows: list[list]) -> None:
    with (EVIDENCE / name).open("w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(cols)
        wr.writerows(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", default="admin")
    ap.add_argument("--since", default=(date.today() - timedelta(days=1)).isoformat(),
                    help="UTC date or timestamp: YYYY-MM-DD or YYYY-MM-DDTHH:MM")
    args = ap.parse_args()
    since_dt = datetime.fromisoformat(args.since)  # rejects non-dates before SQL
    since = since_dt.strftime("%Y-%m-%d %H:%M:%S")
    since_date = since[:10]

    w = dbsql.client(args.profile)
    wid = dbsql.warehouse_id(w)
    users = ", ".join(f"'{u}'" for u in USERS)
    services = ", ".join(f"'{s}'" for s in SERVICES)

    statements = genie_statements(w, since_dt)
    write_generated_sql(statements)
    cols = ["start_time", "user_name", "client_application", "genie_space_id", "status", "rows_produced",
            "query_text"]
    write_csv("query_history.csv", cols, [[q[c] for c in cols] for q in statements])
    print(f"query_history.csv: {len(statements)} rows")

    # The gateway logs each MCP call with the caller and client: Claude-User for the
    # Claude connector, python-httpx2 for client/genie_client.py.
    cols, rows = dbsql.run(w, wid, f"""
        SELECT event_time, requester, user_agent, service_name, mcp_metadata.json_rpc_method AS rpc_method,
               mcp_metadata.tool_name AS tool_name, status_code, latency_ms, request_id
        FROM system.ai_gateway.usage
        WHERE event_time >= '{since}'
          AND requester IN ({users})
          AND service_type = 'MCP_SERVICE'
          AND mcp_metadata.json_rpc_method = 'tools/call'
        ORDER BY event_time""")
    write_csv("gateway_usage.csv", cols, rows)
    print(f"gateway_usage.csv: {len(rows)} rows")
    _, summary = dbsql.run(w, wid, f"""
        SELECT requester, user_agent, mcp_metadata.tool_name, count(*)
        FROM system.ai_gateway.usage
        WHERE event_time >= '{since}' AND requester IN ({users})
          AND service_type = 'MCP_SERVICE' AND mcp_metadata.json_rpc_method = 'tools/call'
        GROUP BY ALL ORDER BY 1, 2, 3""")
    for requester, agent, tool, n in summary:
        print(f"  {requester:18} {agent or '':24} {tool or '':24} {n}")

    cols, rows = dbsql.run(w, wid, f"""
        SELECT event_time, user_identity.email AS email, service_name, action_name, user_agent,
               to_json(request_params) AS request_params, response.status_code AS status_code
        FROM system.access.audit
        WHERE event_date >= '{since_date}' AND event_time >= '{since}'
          AND user_identity.email IN ({users})
          AND service_name IN ({services})
        ORDER BY event_time""")
    write_csv("audit.csv", cols, rows)
    print(f"audit.csv: {len(rows)} rows")
    # user_agent tells the clients apart: Claude-User for the Claude connector,
    # python-httpx2 for client/genie_client.py.
    _, summary = dbsql.run(w, wid, f"""
        SELECT user_identity.email, user_agent, count(*)
        FROM system.access.audit
        WHERE event_date >= '{since_date}' AND event_time >= '{since}'
          AND user_identity.email IN ({users}) AND service_name IN ({services})
        GROUP BY ALL ORDER BY 1, 2""")
    for email, agent, n in summary:
        print(f"  {email:18} {agent or '':24} {n}")


if __name__ == "__main__":
    main()
