-- Row filters: an account manager sees only the accounts they own, and the orders
-- and tickets of those accounts. finance_analysts see every row.
-- Run as admin:  uv run tools/run_sql.py --profile admin sql/03_row_filters.sql
--
-- These are table-level row filters (SET ROW FILTER). The column masks in
-- sql/04_abac.sql are ABAC policies; the two kinds can apply to the same table.
-- Row filters also apply to the table owner and workspace admins, so admin sees
-- no rows once this file has run.

CREATE OR REPLACE FUNCTION poc.governance.account_owner_filter(owner_email STRING)
RETURNS BOOLEAN
COMMENT 'Row filter for customer_accounts: finance_analysts see all rows, everyone else sees the accounts they own.'
RETURN is_account_group_member('finance_analysts') OR owner_email = current_user();

-- Ownership comes from poc.governance.account_owners: a filter cannot read
-- customer_accounts, which has its own filter. The parameter is acct_id so it
-- cannot be confused with the account_id column inside the subquery.
CREATE OR REPLACE FUNCTION poc.governance.child_of_owned_account(acct_id STRING)
RETURNS BOOLEAN
COMMENT 'Row filter for orders and tickets: finance_analysts see all rows, everyone else sees rows for the accounts they own.'
RETURN is_account_group_member('finance_analysts')
  OR EXISTS (
    SELECT 1 FROM poc.governance.account_owners a
    WHERE a.account_id = acct_id AND a.owner_email = current_user()
  );

ALTER TABLE poc.sales.customer_accounts SET ROW FILTER poc.governance.account_owner_filter ON (owner_email);
ALTER TABLE poc.sales.orders            SET ROW FILTER poc.governance.child_of_owned_account ON (account_id);
ALTER TABLE poc.support.tickets         SET ROW FILTER poc.governance.child_of_owned_account ON (account_id);
