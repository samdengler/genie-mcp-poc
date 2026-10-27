"""Shared setup for the live tests against the POC workspace.

Every test runs as one of the Databricks CLI profiles in ~/.databrickscfg, so the
workspace sees the real user. The six logins must be fresh:

    BROWSER=none databricks auth login --host <workspace> --profile <name>

Run all tests, or skip the slow Genie questions and the lagging system tables:

    uv run --with-requirements tests/requirements.txt pytest tests
    uv run --with-requirements tests/requirements.txt pytest tests -m "not genie and not logs"
"""

import sys
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "client"))
sys.path.insert(0, str(ROOT / "demo"))
import dbsql  # noqa: E402

# profile -> the user that profile must sign in as
USERS = {
    "admin": "admin@example.com",
    "alice": "alice@example.com",
    "bob": "bob@example.com",
    "carol": "carol@example.com",
    "david": "david@example.com",
    "frank": "frank@example.com",
}
# The account groups the POC grants on, and who must be in each.
POC_GROUPS = {"account_managers", "finance_analysts", "metastore_admins"}
MEMBERSHIP = {
    "admin": set(),
    "alice": {"account_managers"},
    "bob": {"account_managers"},
    "carol": {"finance_analysts"},
    "david": set(),
    "frank": {"metastore_admins"},
}
ADMITTED = ("alice", "bob", "carol")  # have EXECUTE on Genie One
REFUSED = ("david", "admin", "frank")  # do not

EAST = {f"A{i:03d}" for i in range(1, 13)}  # alice owns these
WEST = {f"A{i:03d}" for i in range(13, 25)}  # bob owns these
VISIBLE_ACCOUNTS = {"alice": EAST, "bob": WEST, "carol": EAST | WEST}

GENIE_ONE_PATH = "/ai-gateway/mcp-services/system.ai.genie_one_mcp"


def pytest_configure(config):
    config.addinivalue_line("markers", "genie: asks Genie One questions over MCP (about two minutes)")
    config.addinivalue_line("markers", "logs: reads system tables, which lag the calls by 20 to 60 minutes")


class Profile:
    """A signed-in CLI profile: its workspace client and its user."""

    def __init__(self, name: str):
        self.name = name
        self.w = dbsql.client(name)
        try:
            self.me = self.w.current_user.me()
        except Exception as err:  # noqa: BLE001
            pytest.fail(f"Profile {name} cannot sign in. Run:\n"
                        f"  BROWSER=none databricks auth login --host <workspace> --profile {name}\n{err}")
        self.user = self.me.user_name
        self.groups = {g.display for g in self.me.groups or []}

    def mcp(self, method: str, params: dict | None = None, rid: int | None = 1,
            session: str | None = None) -> requests.Response:
        """POST one JSON-RPC message to the Genie One MCP URL as this user."""
        headers = {**self.w.config.authenticate(), "Content-Type": "application/json",
                   "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-06-18"}
        if session:
            headers["Mcp-Session-Id"] = session
        body = {"jsonrpc": "2.0", "method": method}
        if rid is not None:
            body["id"] = rid
        if params is not None:
            body["params"] = params
        return requests.post(self.w.config.host.rstrip("/") + GENIE_ONE_PATH, headers=headers, json=body,
                             timeout=60)


@pytest.fixture(scope="session")
def profile():
    """profile("alice") returns that signed-in profile, created once per session."""
    cache: dict[str, Profile] = {}

    def get(name: str) -> Profile:
        if name not in cache:
            cache[name] = Profile(name)
        return cache[name]

    return get


@pytest.fixture(scope="session")
def warehouse_id(profile) -> str:
    # admin can list the warehouse; David has no CAN_USE on it and cannot.
    return dbsql.warehouse_id(profile("admin").w)


@pytest.fixture(scope="session")
def sql(profile, warehouse_id):
    """sql("alice", "SELECT ...") runs one statement as that user and returns (columns, rows)."""

    def run(name: str, statement: str) -> tuple[list[str], list[list]]:
        return dbsql.run(profile(name).w, warehouse_id, statement)

    return run
