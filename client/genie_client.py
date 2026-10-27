# /// script
# requires-python = ">=3.11"
# dependencies = ["databricks-sdk>=0.60", "databricks-mcp>=0.9", "mcp>=2"]
# ///
"""Ask a Genie MCP server a question as one of the CLI profiles.

    uv run client/genie_client.py --profile bob "How many accounts do I have?"
    uv run client/genie_client.py --profile carol --server sales "What was revenue by account last quarter?"
    uv run client/genie_client.py --profile alice --server support --json "Which of my accounts have open high-severity tickets?"

--server picks the MCP server: genie-one (default) is system.ai.genie_one_mcp;
sales and support are the Genie spaces in genie/spaces.json. Authentication is the
profile's OAuth login in ~/.databrickscfg, so the question runs as that user and
Unity Catalog applies that user's row filters and column masks.

--json also writes the question, answer, SQL, and rows to demo/evidence/.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import dbsql  # noqa: E402
import httpx2  # noqa: E402
from databricks_mcp.oauth_provider import DatabricksOAuthClientProvider  # noqa: E402
from mcp import Client  # noqa: E402
from mcp.client.streamable_http import streamable_http_client  # noqa: E402

GENIE_ONE_PATH = "/ai-gateway/mcp-services/system.ai.genie_one_mcp"
POLL_SECONDS = 3
MAX_ROWS_PRINTED = 30


class ClientError(Exception):
    """An error with a message for the person running the client."""


def server_url(host: str, server: str) -> tuple[str, str | None]:
    """Return the MCP URL and, for a Genie space, its space id."""
    if server == "genie-one":
        return host + GENIE_ONE_PATH, None
    spaces = json.loads((ROOT / "genie" / "spaces.json").read_text())
    space_id = spaces[server]["space_id"]
    return f"{host}/api/2.0/mcp/genie/{space_id}", space_id


def error_text(result) -> str:
    return " ".join(getattr(c, "text", "") for c in result.content)


def check(result, who: str, server: str) -> dict:
    """Return the tool result's structured content, or raise a readable error."""
    if result.is_error:
        text = error_text(result)
        if any(s in text for s in ("PERMISSION_DENIED", "does not have", "CAN_RUN", "CAN RUN", "403")):
            raise ClientError(
                f"{who} cannot use the {server} Genie space. A space admin must grant CAN RUN "
                f"on the space (genie/create_spaces.py grants it to both groups).\n{text}")
        raise ClientError(f"{server} returned an error: {text}")
    if result.structured_content is not None:
        return result.structured_content
    return json.loads(error_text(result))


async def ask_genie_one(session, question: str, who: str) -> dict:
    sc = check(await session.call_tool("genie_ask", {"question": question}), who, "genie-one")
    ids = {"conversation_id": sc["conversation_id"], "response_id": sc["response_id"]}
    while sc.get("status") == "in_progress":
        await asyncio.sleep(POLL_SECONDS)
        sc = check(await session.call_tool("genie_poll_response", ids), who, "genie-one")
    queries = []
    for item in sc.get("query_items") or []:
        r = check(await session.call_tool("genie_get_query_result", {**ids, "item_id": item["item_id"]}),
                  who, "genie-one")
        queries.append({"sql": item.get("sql"), "columns": [c["name"] for c in r.get("columns") or []],
                        "rows": r.get("rows") or [], "total_row_count": r.get("total_row_count")})
    return {"status": sc.get("status"), "answer": sc.get("final_answer"), "queries": queries,
            "conversation_id": sc["conversation_id"], "deep_link": sc.get("deep_link")}


async def ask_space(session, space_id: str, question: str, who: str, server: str) -> dict:
    sc = check(await session.call_tool(f"query_space_{space_id}", {"query": question}), who, server)
    while sc.get("status") not in ("COMPLETED", "FAILED", "CANCELLED", "QUERY_RESULT_EXPIRED"):
        await asyncio.sleep(POLL_SECONDS)
        sc = check(await session.call_tool(f"poll_response_{space_id}", {
            "conversation_id": sc["conversationId"], "message_id": sc["messageId"]}), who, server)
    content = sc.get("content") or {}
    queries = []
    for q in content.get("queryAttachments") or []:
        resp = q.get("statement_response") or {}
        cols = [c["name"] for c in ((resp.get("manifest") or {}).get("schema") or {}).get("columns") or []]
        rows = [[v.get("string_value") for v in r.get("values", [])]
                for r in (resp.get("result") or {}).get("data_array") or []]
        queries.append({"sql": q.get("query"), "description": q.get("description"), "columns": cols,
                        "rows": rows, "total_row_count": (resp.get("manifest") or {}).get("total_row_count")})
    return {"status": sc.get("status"), "answer": "\n\n".join(content.get("textAttachments") or []),
            "queries": queries, "conversation_id": sc.get("conversationId"),
            "deep_link": f"{HOST}/genie/rooms/{space_id}/chats/{sc.get('conversationId')}"}


async def ask(w, url: str, space_id: str | None, server: str, question: str, who: str, timeout: float) -> dict:
    auth = DatabricksOAuthClientProvider(w)
    # The space tools hold the request open until Genie answers, so the read timeout
    # has to cover a full Genie turn. httpx's 5 second default does not.
    async with httpx2.AsyncClient(auth=auth, follow_redirects=True, timeout=httpx2.Timeout(timeout)) as http:
        async with Client(streamable_http_client(url, http_client=http)) as session:
            if space_id:
                return await ask_space(session, space_id, question, who, server)
            return await ask_genie_one(session, question, who)


def root_cause(err: BaseException) -> BaseException:
    while isinstance(err, BaseExceptionGroup) and err.exceptions:
        err = err.exceptions[0]
    return err


def explain(err: BaseException, profile: str) -> str:
    text = str(err)
    login = (f"Run: BROWSER=none databricks auth login --host {HOST} --profile {profile}\n"
             f"and open the printed URL in a private window signed in as that user.")
    if any(s in text.lower() for s in ("cannot get access token", "invalid access token", "invalid_grant",
                                        "refresh token", "token is expired", "token expired", "401")):
        return f"The OAuth login for profile {profile} has expired or is invalid.\n{login}\n\n{text}"
    if any(s in text for s in ("Not authorized to invoke MCP service", "permission to use mcp service")):
        return (f"Unity Gateway refused profile {profile}: it has no EXECUTE on the MCP service. "
                f"sql/07_gateway.sql grants EXECUTE on system.ai.genie_one_mcp to account_managers "
                f"and finance_analysts only.\n\n{text}")
    if "403" in text or "PERMISSION_DENIED" in text:
        return (f"Profile {profile} is not allowed to use this MCP server. For a Genie space the user "
                f"needs CAN RUN on the space.\n\n{text}")
    return f"{type(err).__name__}: {text}"


def print_result(rec: dict) -> None:
    print(f"user:     {rec['user']}")
    print(f"server:   {rec['server']} ({rec['url']})")
    print(f"question: {rec['question']}")
    print(f"status:   {rec['status']}  ({rec['seconds']}s)")
    print(f"\n{rec['answer'] or '(no text answer)'}\n")
    for i, q in enumerate(rec["queries"], 1):
        print(f"--- query {i} ---\n{q['sql']}\n")
        if q["columns"]:
            cells = [["NULL" if v is None else str(v) for v in r] for r in q["rows"][:MAX_ROWS_PRINTED]]
            widths = [max([len(c)] + [len(r[j]) for r in cells]) for j, c in enumerate(q["columns"])]
            print("  ".join(c.ljust(widths[j]) for j, c in enumerate(q["columns"])))
            print("  ".join("-" * wd for wd in widths))
            for r in cells:
                print("  ".join(v.ljust(widths[j]) for j, v in enumerate(r)))
            more = len(q["rows"]) - len(cells)
            print(f"({len(q['rows'])} rows{f', {more} not shown' if more > 0 else ''})\n")
    if rec.get("deep_link"):
        print(f"open in Databricks: {rec['deep_link']}")


def main() -> None:
    global HOST
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", required=True, help="Databricks CLI profile (alice, bob, carol, admin)")
    ap.add_argument("--server", default="genie-one", choices=["genie-one", "sales", "support"])
    ap.add_argument("--json", action="store_true", help="also write the result to demo/evidence/")
    ap.add_argument("--timeout", type=float, default=300, help="seconds to wait for one MCP request")
    ap.add_argument("question")
    args = ap.parse_args()

    try:
        w = dbsql.client(args.profile)
        HOST = w.config.host.rstrip("/")
        who = w.current_user.me().user_name
    except Exception as err:  # noqa: BLE001
        sys.exit(explain(err, args.profile))

    url, space_id = server_url(HOST, args.server)
    started = time.time()
    try:
        result = asyncio.run(ask(w, url, space_id, args.server, args.question, who, args.timeout))
    except ClientError as err:
        sys.exit(str(err))
    except BaseException as err:  # noqa: BLE001  (anyio wraps failures in exception groups)
        if isinstance(err, KeyboardInterrupt):
            raise
        sys.exit(explain(root_cause(err), args.profile))

    rec = {"asked_at": datetime.now().astimezone().isoformat(timespec="seconds"), "profile": args.profile,
           "user": who, "server": args.server, "url": url, "question": args.question,
           "seconds": round(time.time() - started), **result}
    print_result(rec)
    if args.json:
        out = ROOT / "demo" / "evidence" / f"{datetime.now():%Y%m%d-%H%M%S}_{args.profile}_{args.server}.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rec, indent=2) + "\n")
        print(f"wrote {out.relative_to(ROOT)}")


HOST = ""

if __name__ == "__main__":
    main()
