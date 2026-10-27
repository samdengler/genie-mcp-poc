"""Genie One answers each business user as that user, and Unity Catalog shapes every result.

The tests ask Genie One over MCP with client/genie_client.py, read the SQL Genie ran
from the Query History API, and run each statement again as the same user. They
check outcomes (which accounts come back, which values are masked) because Genie's
wording and SQL change from run to run.
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from databricks.sdk.service import sql as sqlapi

import genie_client
from collect_evidence import governance_in
from conftest import ADMITTED, GENIE_ONE_PATH, VISIBLE_ACCOUNTS

pytestmark = pytest.mark.genie

SALES = "Which of my accounts had the most revenue last quarter, and who is the contact?"
CROSS = "Which of my accounts have an open high-severity support ticket, and what did they order last quarter?"
ASKS = [("alice", SALES), ("bob", SALES), ("carol", SALES), ("alice", CROSS), ("bob", CROSS)]
OWNERS = ("alice", "bob")  # account managers: contacts in clear, money masked
EMAIL_COLUMNS = ("contact_email", "reporter_email")


def is_money(column: str) -> bool:
    return any(word in column.lower() for word in ("revenue", "amount"))


def genie_statements(admin, p, since_ms: int) -> list[sqlapi.QueryInfo]:
    """Genie's SELECT statements run as this user since a time, from the Query History API.

    Read as admin: the API shows a user their own Genie statements as <REDACTED>.
    """
    kwargs = {"filter_by": sqlapi.QueryFilter(query_start_time_range=sqlapi.TimeRange(start_time_ms=since_ms),
                                              user_ids=[int(p.me.id)])}
    found = []
    while True:
        page = admin.w.query_history.list(max_results=1000, **kwargs)
        found += [q for q in page.res or [] if q.statement_type and q.statement_type.value == "SELECT"
                  and "genie" in (q.client_application or "").lower()]
        if not page.has_next_page:
            return found
        kwargs = {"page_token": page.next_page_token}


@pytest.fixture(scope="module")
def run(profile):
    """Ask every question once, in parallel, and collect each user's Genie statements."""
    since_ms = int(time.time() * 1000)

    def ask(name: str, question: str) -> dict:
        p = profile(name)
        url = p.w.config.host.rstrip("/") + GENIE_ONE_PATH
        return asyncio.run(genie_client.ask(p.w, url, None, "genie-one", question, p.user, 300))

    for name, _ in ASKS:
        profile(name)  # sign in before the threads start
    with ThreadPoolExecutor(len(ASKS)) as pool:
        answers = dict(zip(ASKS, pool.map(lambda a: ask(*a), ASKS)))

    # Statements reach the Query History API within seconds of running.
    statements = {}
    for name in ADMITTED:
        for _ in range(12):
            statements[name] = genie_statements(profile("admin"), profile(name), since_ms)
            if statements[name]:
                break
            time.sleep(5)
    return {"answers": answers, "statements": statements}


@pytest.mark.parametrize("ask", ASKS, ids=[f"{n}-{'sales' if q == SALES else 'cross'}" for n, q in ASKS])
def test_genie_one_answers(run, ask):
    answer = run["answers"][ask]
    assert answer["status"] == "completed", answer
    assert answer["answer"]


@pytest.mark.parametrize("name", ADMITTED)
def test_genie_ran_sql_as_the_user_who_asked(run, profile, name):
    statements = run["statements"][name]
    assert statements, f"no Genie statements for {name} in the Query History API"
    assert {q.user_name for q in statements} == {profile(name).user}
    assert {q.executed_as_user_name for q in statements} == {profile(name).user}


@pytest.mark.parametrize("name", ADMITTED)
def test_statement_text_is_readable(run, name):
    """Guards the SQL checks below: a redacted statement would pass them without being read."""
    redacted = [q.query_id for q in run["statements"][name] if "FROM" not in (q.query_text or "").upper()]
    assert not redacted


@pytest.mark.parametrize("name", ADMITTED)
def test_genie_sql_holds_no_access_logic(run, name):
    found = {q.query_text: governance_in(q.query_text or "") for q in run["statements"][name]}
    assert not {sql: tokens for sql, tokens in found.items() if tokens}


@pytest.mark.parametrize("name", ADMITTED)
def test_results_respect_row_filters_and_masks(run, sql, name):
    """Run each of Genie's statements again as the same user and check what comes back."""
    money_values, checked = [], set()
    # Genie sometimes retries after a statement fails; only the ones that ran produced results.
    finished = [q for q in run["statements"][name] if q.status == sqlapi.QueryStatus.FINISHED]
    assert finished
    for q in finished:
        cols, rows = sql(name, q.query_text)
        for i, col in enumerate(cols):
            values = [r[i] for r in rows]
            if col.lower() == "account_id" or col.lower() in EMAIL_COLUMNS or is_money(col):
                checked.add(col.lower())
            if col.lower() == "account_id":
                assert set(values) <= VISIBLE_ACCOUNTS[name], f"{col} outside {name}'s accounts in:\n{q.query_text}"
            if col.lower() in EMAIL_COLUMNS:
                emails = [v for v in values if v is not None]
                if name in OWNERS:
                    assert not any(v.startswith("***") for v in emails), f"{col} masked for an owner"
                else:
                    assert all(v.startswith("***@") for v in emails), f"{col} in clear for {name}"
            if is_money(col):
                money_values += values
                if name in OWNERS:
                    assert all(v is None for v in values), f"{col} visible to {name} in:\n{q.query_text}"
    assert checked, f"no account, email, or money column came back for {name}, so nothing was checked"
    if name not in OWNERS:
        assert any(v is not None for v in money_values), "finance_analysts should see revenue"
