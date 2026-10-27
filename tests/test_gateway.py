"""Unity Gateway admits the two business groups to Genie One and refuses everyone else.

The refusal tests send raw JSON-RPC requests, so they show what the gateway itself
answers before any MCP client library is involved.
"""

import asyncio

import pytest

import genie_client
from conftest import ADMITTED, GENIE_ONE_PATH, REFUSED

INIT = {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "genie-mcp-poc-tests", "version": "1"}}
REFUSALS = {
    "david": "Not authorized to invoke MCP service.",
    "admin": "Not authorized to invoke MCP service.",
    # MANAGE on system.ai lets Frank see the service, so the message differs.
    "frank": "User does not have permission to use mcp service 'system.ai.genie_one_mcp'",
}


def grants(sql, statement: str) -> set[tuple[str, str]]:
    cols, rows = sql("frank", statement)
    i, j = cols.index("Principal"), cols.index("ActionType")
    return {(r[i], r[j]) for r in rows}


def test_only_the_business_groups_hold_execute_on_genie_one(sql):
    on_service = grants(sql, "SHOW GRANTS ON MCP SERVICE system.ai.genie_one_mcp")
    assert {p for p, a in on_service if a == "EXECUTE"} == {"account_managers", "finance_analysts"}


def test_account_users_lost_the_default_execute_on_system_ai(sql):
    on_schema = grants(sql, "SHOW GRANTS ON SCHEMA system.ai")
    assert ("account users", "EXECUTE") not in on_schema
    assert ("metastore_admins", "MANAGE") in on_schema


@pytest.mark.parametrize("name", ADMITTED)
def test_gateway_admits_the_business_users(profile, name):
    p = profile(name)
    init = p.mcp("initialize", INIT)
    assert init.status_code == 200, init.text
    assert init.json()["result"]["serverInfo"]["name"]
    session = init.headers.get("mcp-session-id")
    assert p.mcp("notifications/initialized", rid=None, session=session).status_code in (200, 202, 204)
    tools = p.mcp("tools/list", {}, rid=2, session=session)
    assert tools.status_code == 200, tools.text
    assert {"genie_ask", "genie_poll_response"} <= {t["name"] for t in tools.json()["result"]["tools"]}


def test_mcp_client_reports_the_refusal(profile):
    """The Python client a user would run gets the gateway's refusal, not an answer."""
    p = profile("david")
    url = p.w.config.host.rstrip("/") + GENIE_ONE_PATH
    with pytest.raises(BaseException) as refused:
        asyncio.run(genie_client.ask(p.w, url, None, "genie-one", "How many accounts do I have?", p.user, 60))
    assert "Not authorized to invoke MCP service." in str(genie_client.root_cause(refused.value))


@pytest.mark.parametrize("name", REFUSED)
@pytest.mark.parametrize("method,params", [
    ("initialize", INIT),
    ("tools/list", {}),
    ("tools/call", {"name": "genie_ask", "arguments": {"question": "How many accounts do I have?"}}),
])
def test_gateway_refuses_everyone_else(profile, name, method, params):
    r = profile(name).mcp(method, params)
    assert r.status_code == 403, r.text
    error = r.json()["error"]
    assert error["code"] == -32007
    assert error["message"] == REFUSALS[name]
