-- Read access for the two groups. The row filters and masks decide what each
-- member sees.
-- Run as admin:  uv run tools/run_sql.py --profile admin sql/05_grants.sql

GRANT USE CATALOG ON CATALOG poc TO `account_managers`;
GRANT USE CATALOG ON CATALOG poc TO `finance_analysts`;

GRANT USE SCHEMA ON SCHEMA poc.sales      TO `account_managers`;
GRANT USE SCHEMA ON SCHEMA poc.sales      TO `finance_analysts`;
GRANT USE SCHEMA ON SCHEMA poc.support    TO `account_managers`;
GRANT USE SCHEMA ON SCHEMA poc.support    TO `finance_analysts`;
GRANT USE SCHEMA ON SCHEMA poc.governance TO `account_managers`;
GRANT USE SCHEMA ON SCHEMA poc.governance TO `finance_analysts`;

GRANT SELECT ON TABLE poc.sales.customer_accounts TO `account_managers`;
GRANT SELECT ON TABLE poc.sales.customer_accounts TO `finance_analysts`;
GRANT SELECT ON TABLE poc.sales.orders            TO `account_managers`;
GRANT SELECT ON TABLE poc.sales.orders            TO `finance_analysts`;
GRANT SELECT ON TABLE poc.support.tickets         TO `account_managers`;
GRANT SELECT ON TABLE poc.support.tickets         TO `finance_analysts`;

-- EXECUTE on the whole governance schema covers the filter and mask functions.
GRANT EXECUTE ON SCHEMA poc.governance TO `account_managers`;
GRANT EXECUTE ON SCHEMA poc.governance TO `finance_analysts`;
