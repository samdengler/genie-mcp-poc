-- Column masks as ABAC policies on catalog poc. Each policy finds its columns by
-- governed tag (sql/02_tags.sql), so a newly tagged column is masked with no
-- change here.
-- Run as admin:  uv run tools/run_sql.py --profile admin sql/04_abac.sql
--
--   classification = PII           masked unless the reader owns the account
--                                  (an email keeps its domain: ***@domain)
--   classification = Confidential  NULL unless the reader is in finance_analysts
--
-- ABAC policies need serverless compute or Databricks Runtime 16.4 or above.

-- Ownership comes from poc.governance.account_owners: a mask cannot read
-- customer_accounts, which has a row filter.
CREATE OR REPLACE FUNCTION poc.governance.pii_mask(value STRING, acct_id STRING)
RETURNS STRING
COMMENT 'PII mask: the owner of the row''s account sees the value, everyone else sees ***@domain or ***.'
RETURN CASE
  WHEN EXISTS (
    SELECT 1 FROM poc.governance.account_owners a
    WHERE a.account_id = acct_id AND a.owner_email = current_user()
  ) THEN value
  WHEN value LIKE '%@%' THEN concat('***@', substring_index(value, '@', -1))
  ELSE '***'
END;

CREATE OR REPLACE FUNCTION poc.governance.confidential_mask(value DECIMAL(18,2))
RETURNS DECIMAL(18,2)
COMMENT 'Confidential mask: finance_analysts see the value, everyone else sees NULL.'
RETURN CASE WHEN is_account_group_member('finance_analysts') THEN value END;

-- Every MATCH COLUMNS alias must match in a table the policy applies to: a table
-- with a PII column but no row_owner column fails with UC_ABAC_UNMATCHED_USING_ALIAS.
CREATE OR REPLACE POLICY pii_owner_only
ON CATALOG poc
COMMENT 'Mask PII columns for everyone except the owner of the row''s account.'
COLUMN MASK poc.governance.pii_mask
TO `account users`
FOR TABLES
MATCH COLUMNS has_tag_value('classification', 'PII') AS pii,
              has_tag_value('row_owner', 'account_id') AS acct
ON COLUMN pii
USING COLUMNS (acct);

CREATE OR REPLACE POLICY confidential_finance_only
ON CATALOG poc
COMMENT 'Hide Confidential columns from everyone outside finance_analysts.'
COLUMN MASK poc.governance.confidential_mask
TO `account users`
FOR TABLES
MATCH COLUMNS has_tag_value('classification', 'Confidential') AS conf
ON COLUMN conf;
