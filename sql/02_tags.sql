-- Tag the columns that the ABAC policies in sql/04_abac.sql match on.
-- Run as admin after sql/02_governed_tags.sql:
--   uv run tools/run_sql.py --profile admin sql/02_tags.sql
-- SET TAGS overwrites the value, so the file can be rerun.

ALTER TABLE poc.sales.customer_accounts ALTER COLUMN contact_email  SET TAGS ('classification' = 'PII');
ALTER TABLE poc.sales.customer_accounts ALTER COLUMN contact_phone  SET TAGS ('classification' = 'PII');
ALTER TABLE poc.sales.customer_accounts ALTER COLUMN annual_revenue SET TAGS ('classification' = 'Confidential');
ALTER TABLE poc.sales.orders            ALTER COLUMN amount         SET TAGS ('classification' = 'Confidential');
ALTER TABLE poc.support.tickets         ALTER COLUMN reporter_email SET TAGS ('classification' = 'PII');

-- The column the PII mask policy passes to its mask function to find the owner.
-- Every table with a PII column needs one.
ALTER TABLE poc.sales.customer_accounts ALTER COLUMN account_id  SET TAGS ('row_owner' = 'account_id');
ALTER TABLE poc.support.tickets         ALTER COLUMN account_id  SET TAGS ('row_owner' = 'account_id');
