"""Unity Catalog row filters, column masks, and grants, checked by querying as each user."""

import pytest
from databricks.sdk.errors import PermissionDenied

import dbsql
from conftest import ROOT

VERIFY_CHECKS = 16  # rows in the first result of each sql/verify/<user>.sql


@pytest.mark.parametrize("name", ["alice", "bob", "carol"])
def test_verify_sql_checks_pass(sql, name):
    """The 16 checks in sql/verify/<user>.sql: row counts, masks, and join leakage."""
    checks = dbsql.split_statements((ROOT / "sql" / "verify" / f"{name}.sql").read_text())[0]
    cols, rows = sql(name, checks)
    results = [dict(zip(cols, r)) for r in rows]
    assert len(results) == VERIFY_CHECKS
    failed = [f"{r['check']}: expected {r['expected']}, got {r['actual']}" for r in results if r["pass"] != "true"]
    assert not failed, "\n".join(failed)


def test_admin_sees_no_accounts_through_the_row_filter(sql):
    """The account admin owns the tables but owns no accounts and is in neither group."""
    _, rows = sql("admin", "SELECT count(*) FROM poc.sales.customer_accounts")
    assert rows[0][0] == "0"


@pytest.mark.parametrize("name", ["alice", "bob", "carol"])
def test_readers_cannot_query_the_ownership_lookup(sql, name):
    with pytest.raises(RuntimeError, match="(?i)permission|privilege|does not have"):
        sql(name, "SELECT count(*) FROM poc.governance.account_owners")


def test_david_has_no_access_to_the_poc_catalog(profile):
    with pytest.raises(PermissionDenied, match="USE CATALOG"):
        profile("david").w.tables.get("poc.sales.customer_accounts")


def test_metastore_admin_cannot_read_poc_data(sql):
    """Frank governs Unity Catalog but holds no data grants on poc."""
    with pytest.raises(RuntimeError, match="USE CATALOG"):
        sql("frank", "SELECT count(*) FROM poc.sales.customer_accounts")
