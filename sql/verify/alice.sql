-- Governance check for alice@example.com (account_managers).
--   uv run tools/run_sql.py --profile alice sql/verify/alice.sql
--
--   alice owns the 12 East accounts, so the row filters keep only those
--   accounts and their orders and tickets. As the owner, alice sees contact
--   email, phone, and ticket reporter email in clear. annual_revenue and
--   orders.amount are Confidential and come back NULL (alice is not in finance_analysts).
--
-- Every row of the first result must have pass = true. The second result shows
-- sample rows for the record.

WITH a AS (SELECT * FROM poc.sales.customer_accounts),
o AS (SELECT * FROM poc.sales.orders),
t AS (SELECT * FROM poc.support.tickets),
checks AS (
  SELECT 'current_user' AS check, 'alice@example.com' AS expected, current_user() AS actual
  UNION ALL SELECT 'accounts visible',             '12', CAST(count(*) AS STRING) FROM a
  UNION ALL SELECT 'East accounts',                '12', CAST(count_if(region = 'East') AS STRING) FROM a
  UNION ALL SELECT 'West accounts',                '0', CAST(count_if(region = 'West') AS STRING) FROM a
  UNION ALL SELECT 'contact_email in clear',       '12', CAST(count_if(contact_email NOT LIKE '***%') AS STRING) FROM a
  UNION ALL SELECT 'contact_email as ***@domain',  '0', CAST(count_if(contact_email LIKE '***@%.example') AS STRING) FROM a
  UNION ALL SELECT 'contact_phone in clear',       '12', CAST(count_if(contact_phone <> '***') AS STRING) FROM a
  UNION ALL SELECT 'annual_revenue not NULL',      '0', CAST(count(annual_revenue) AS STRING) FROM a
  UNION ALL SELECT 'orders visible',               '60', CAST(count(*) AS STRING) FROM o
  UNION ALL SELECT 'orders.amount not NULL',       '0', CAST(count(amount) AS STRING) FROM o
  UNION ALL SELECT 'tickets visible',              '24', CAST(count(*) AS STRING) FROM t
  UNION ALL SELECT 'reporter_email in clear',      '24', CAST(count_if(reporter_email NOT LIKE '***%') AS STRING) FROM t
  UNION ALL SELECT 'reporter_email as ***@domain', '0', CAST(count_if(reporter_email LIKE '***@%.example') AS STRING) FROM t
  -- Joins cannot reach rows the filter removed: every visible order and ticket
  -- belongs to a visible account.
  UNION ALL SELECT 'orders without a visible account',  '0', CAST(count(*) AS STRING) FROM o LEFT ANTI JOIN a USING (account_id)
  UNION ALL SELECT 'tickets without a visible account', '0', CAST(count(*) AS STRING) FROM t LEFT ANTI JOIN a USING (account_id)
  UNION ALL SELECT 'revenue sum through join is NULL', 'true',
    CAST(sum(o.amount) IS NULL AS STRING) FROM o JOIN a USING (account_id)
)
SELECT check, expected, actual, expected = actual AS pass FROM checks;

SELECT account_id, account_name, region, owner_email, contact_email, contact_phone, annual_revenue
FROM poc.sales.customer_accounts
ORDER BY account_id
LIMIT 3;
