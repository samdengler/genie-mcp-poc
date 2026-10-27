# Demo script

Three people ask Genie One the same question through the same MCP server, `system.ai.genie_one_mcp`. Alice asks in Claude; Bob and Carol ask through the Python client. Unity Gateway decides who may call Genie One, and Unity Catalog decides what each caller sees. A fourth user, David, is in neither business group, and the gateway refuses him. Claude, the MCP server, and Genie carry no governance logic.

Workspace: https://<workspace-host>. The Genie One MCP URL and space ids are in the README.

## Before the demo

1. Refresh the CLI logins so no token expires mid-demo. Open each printed URL in a private window signed in as that user:

   ```
   HOST=https://<workspace-host>
   BROWSER=none databricks auth login --host $HOST --profile bob
   BROWSER=none databricks auth login --host $HOST --profile carol
   BROWSER=none databricks auth login --host $HOST --profile david
   ```

2. Note the UTC start time, for `demo/collect_evidence.py --since`.
3. Lay out four windows side by side:
   - Claude (desktop or claude.ai), signed in to the Claude account whose Genie One connector is signed in to Databricks as alice. In the chat's connectors menu, check that Genie One is on.
   - Terminal 1 for Bob and David, terminal 2 for Carol, both in the repo root.
   - A Databricks tab signed in as admin, with the SQL editor open.

## Step 1: Alice asks in Claude

In Claude:

> Using the Genie One connector, call genie_ask and genie_poll_response (not view_ask), then summarize the answer for me: Which of my accounts had the most revenue last quarter, and who is the contact?

Expected: Alice's 12 East accounts (A001 to A012) with contact names and real contact emails. Revenue is masked for account managers, so Genie says so and ranks by order count instead: Birchwood Foods (A002) with 4 orders in Q3 2026, contact Blake Hughes.

Point at: the `genie_ask` and `genie_poll_response` tool calls in Claude; the East accounts only; the contacts in clear; the missing revenue.

Without the tool hint, Claude picks `view_ask`, which renders Genie's steps, result tables, and answer in a panel inside the chat. The panel shows the SQL results well, but Claude's own reply then only says "Asking Genie now", and the panel shows raw `:citation[...]` and `:embedTable[...]` markers.

## Step 2: Bob asks the same question

Terminal 1:

```
uv run client/genie_client.py --profile bob --json "Which of my accounts had the most revenue last quarter, and who is the contact?"
```

Expected: one of Bob's 12 West accounts (A013 to A024) with the contact in clear and revenue NULL. Genie returns A013 Maple Street Bank: every revenue value is NULL, so the sort falls back to account id.

Point at: the same question, the same MCP server as Alice's Claude connector, a different identity, and rows that don't overlap with Alice's. Genie's note that the ranking "is still reliable" is wrong; with revenue masked there is no ranking.

## Step 3: Carol asks the same question

Terminal 2:

```
uv run client/genie_client.py --profile carol --json "Which of my accounts had the most revenue last quarter, and who is the contact?"
```

Expected: revenue for accounts in both regions. The top account is Birchwood Foods (A002, $571,135.77 in Q3 2026), and every contact email reads `***@<domain>`.

Point at: revenue is present; every email is masked. Carol sees all the rows but none of the contacts.

## Step 4: David is refused at the gateway

Terminal 1:

```
uv run client/genie_client.py --profile david "Which of my accounts had the most revenue last quarter, and who is the contact?"
```

Expected:

```
Unity Gateway refused profile david: it has no EXECUTE on the MCP service. sql/07_gateway.sql grants EXECUTE on system.ai.genie_one_mcp to account_managers and finance_analysts only.

Not authorized to invoke MCP service.
```

The gateway answers HTTP 403 with JSON-RPC error `-32007` to every request, starting with `initialize`. Genie never runs, so no SQL reaches Unity Catalog.

Point at: who may call Genie One is decided at the gateway, by a Unity Catalog grant on the MCP service. In the SQL editor as admin:

```sql
SHOW GRANTS ON MCP SERVICE system.ai.genie_one_mcp;   -- EXECUTE: account_managers, finance_analysts
```

Frank, the metastore admin, set those grants with `sql/07_gateway.sql`. He holds MANAGE on `system.ai` but no EXECUTE, so the gateway refuses him too. The account admin (`admin@example.com`) is refused the same way.

## Step 5: The SQL Genie wrote

Run the evidence collector (step 8) or open SQL > Query History in Databricks as admin, filtered to alice, bob, and carol. `demo/evidence/generated_sql.md` lists every statement with a check for ownership or masking logic.

Expected: plain queries over `revenue_by_account`, `customer_accounts`, `orders`, and `tickets`. There's no `owner_email` predicate, no `current_user()`, and no `CASE` for masking. Genie One sometimes answers from the tables directly (client application `DatabricksGenie`) and sometimes hands the question to the POC Sales space (`Databricks SQL Genie Space`); the SQL is clean either way.

Point at: Unity Catalog adds the row filter and masks when the query runs. In the SQL editor as admin:

```sql
DESCRIBE TABLE EXTENDED poc.sales.customer_accounts;   -- Row Filter: poc.governance.account_owner_filter
SHOW POLICIES ON CATALOG poc;                          -- pii_owner_only, confidential_finance_only
```

## Step 6: The gateway log

Every Genie One tool call passes through Unity Gateway, which logs the caller and the client. In the SQL editor as admin, replacing the start time:

```sql
SELECT event_time, requester, user_agent, mcp_metadata.tool_name AS tool, status_code
FROM system.ai_gateway.usage
WHERE event_time >= '<start time UTC>'
  AND service_type = 'MCP_SERVICE'
  AND mcp_metadata.json_rpc_method = 'tools/call'
  AND requester IN ('alice@example.com', 'bob@example.com', 'carol@example.com')
ORDER BY event_time;
```

Expected: `genie_ask` and `genie_poll_response` calls for alice with user agent `Claude-User`, and for bob and carol with `python-httpx2`. David's refused requests are in `demo/evidence/gateway_refusals.txt` with their request ids.

The gateway table lags by 20 to 30 minutes. If the rows aren't there yet, come back to this step at the end. `system.query.history` ran more than two days behind on this trial workspace, so the SQL comes from the Query History API instead (step 5).

## Step 7: Cross-space question

In Claude:

> Using the Genie One connector, call genie_ask and genie_poll_response (not view_ask), then summarize the answer for me: Which of my accounts have an open high-severity support ticket, and what did they order last quarter?

Expected for Alice: A002 Birchwood Foods and A005 Evergreen Clinics, with their 7 Q3 2026 orders and amounts NULL. Genie One reads both the tickets and the sales tables.

Then Bob, terminal 1:

```
uv run client/genie_client.py --profile bob --json "Which of my accounts have an open high-severity support ticket, and what did they order last quarter?"
```

Expected for Bob: A014 Northwind Outfitters and A019 Sable Security, with reporter emails in clear (he owns the accounts) and order amounts NULL.

Point at: one question joined across sales and support, with the same filters and masks on both.

## Step 8: Collect the evidence

```
uv run demo/collect_evidence.py --since <start time UTC, e.g. 2026-10-26T22:30>
```

This writes `generated_sql.md`, `query_history.csv`, `gateway_usage.csv`, and `audit.csv` to `demo/evidence/`. Save screenshots there too:
- Alice's two answers in Claude.
- Bob's, Carol's, and David's terminals.
- The gateway log query result.
