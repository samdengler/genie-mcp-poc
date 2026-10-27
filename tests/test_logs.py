"""The audit log and the gateway log name the user behind each Genie One call.

System tables lag the calls by 20 to 60 minutes, so these tests look back over the
last GENIE_POC_LOG_DAYS days (default 7) rather than at this test run. Claude can't
be driven from a test; the Claude test checks the record that a manual Claude run
(demo/script.md, step 1) leaves in the gateway log.
"""

import os

import pytest

from conftest import ADMITTED, REFUSED, USERS

pytestmark = pytest.mark.logs

DAYS = int(os.environ.get("GENIE_POC_LOG_DAYS", "7"))
TOOL_CALLS = f"""
    FROM system.ai_gateway.usage
    WHERE event_time >= current_timestamp() - INTERVAL {DAYS} DAYS
      AND service_type = 'MCP_SERVICE'
      AND mcp_metadata.json_rpc_method = 'tools/call'"""


def count(sql, statement: str) -> int:
    _, rows = sql("admin", statement)
    return int(rows[0][0])


def test_claude_calls_reach_genie_one_as_alice(sql):
    assert count(sql, f"""SELECT count(*) {TOOL_CALLS}
        AND requester = '{USERS["alice"]}' AND user_agent LIKE 'Claude-User%' AND status_code = 200""") > 0


@pytest.mark.parametrize("name", ADMITTED)
def test_gateway_log_names_each_client_user(sql, name):
    assert count(sql, f"""SELECT count(*) {TOOL_CALLS}
        AND requester = '{USERS[name]}' AND user_agent LIKE 'python-httpx%' AND status_code = 200""") > 0


@pytest.mark.parametrize("name", REFUSED)
def test_audit_log_records_each_refusal(sql, name):
    assert count(sql, f"""SELECT count(*) FROM system.access.audit
        WHERE event_date >= current_date() - {DAYS}
          AND service_name = 'mcpService' AND action_name = 'mcpCall'
          AND user_identity.email = '{USERS[name]}' AND response.status_code = 403""") > 0


@pytest.fixture(scope="module")
def grant_change(sql):
    """When and by whom the default EXECUTE on system.ai was revoked, from the audit log."""
    _, rows = sql("admin", f"""
        SELECT event_time, user_identity.email FROM system.access.audit
        WHERE event_date >= current_date() - {DAYS}
          AND service_name = 'unityCatalog' AND action_name = 'updatePermissions'
          AND request_params['securable_full_name'] = 'system.ai'
          AND request_params['changes'] LIKE '%account users%remove%EXECUTE%'
        ORDER BY event_time DESC LIMIT 1""")
    if not rows:
        pytest.skip(f"no revoke of EXECUTE on system.ai in the last {DAYS} days")
    return {"time": rows[0][0], "by": rows[0][1]}


def test_audit_log_names_the_metastore_admin_for_the_grant_change(grant_change):
    assert grant_change["by"] == USERS["frank"]


@pytest.mark.parametrize("name", REFUSED)
def test_no_refused_user_called_genie_one_after_the_grant_change(sql, grant_change, name):
    assert count(sql, f"""SELECT count(*) {TOOL_CALLS}
        AND requester = '{USERS[name]}' AND status_code = 200
        AND event_time > '{grant_change["time"]}'""") == 0
