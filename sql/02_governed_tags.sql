-- Governed tags for the ABAC column mask policies in sql/04_abac.sql.
-- Run once as admin:  uv run tools/run_sql.py --profile admin sql/02_governed_tags.sql
--
-- Governed tags are account-level objects. CREATE GOVERNED TAG has no IF NOT EXISTS
-- or OR REPLACE form, so a second run fails with an already-exists error. Use
-- SHOW GOVERNED TAGS to check, and ALTER GOVERNED TAG ... SET VALUES to change values.

-- What kind of data a column holds. PII columns are masked unless the reader owns
-- the account; Confidential columns are hidden from everyone outside finance_analysts.
CREATE GOVERNED TAG classification
DESCRIPTION 'Data classification that drives column masks in catalog poc'
VALUES ('PII', 'Confidential');

-- The column that identifies a row's account, so the PII mask policy can pass it
-- to the mask function, which looks up the owner in poc.governance.account_owners.
CREATE GOVERNED TAG row_owner
DESCRIPTION 'Column that identifies the account owner, passed to the PII mask in catalog poc'
VALUES ('account_id');
