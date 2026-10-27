-- Catalog, schemas, and tables for the Genie MCP governance POC.
-- Run as admin:  uv run tools/run_sql.py --profile admin sql/01_schema.sql
--
-- Genie reads table and column comments as its business glossary, so every
-- table and column carries one.

CREATE CATALOG IF NOT EXISTS poc
COMMENT 'Genie MCP governance POC: synthetic sales and support data.';

CREATE SCHEMA IF NOT EXISTS poc.sales
COMMENT 'Customer accounts and their orders. Covered by the Sales Genie space.';

CREATE SCHEMA IF NOT EXISTS poc.support
COMMENT 'Customer support tickets. Covered by the Support Genie space.';

CREATE SCHEMA IF NOT EXISTS poc.governance
COMMENT 'Row filter and column mask functions applied to the sales and support tables.';

CREATE TABLE IF NOT EXISTS poc.sales.customer_accounts (
  account_id     STRING        NOT NULL COMMENT 'Unique account identifier, for example A001. Join key to orders and support tickets.',
  account_name   STRING        NOT NULL COMMENT 'Name of the customer company.',
  region         STRING        NOT NULL COMMENT 'Sales region of the account: East or West.',
  owner_email    STRING        NOT NULL COMMENT 'Email of the account manager who owns this account. Used for row-level access.',
  contact_name   STRING                 COMMENT 'Name of the primary contact at the customer.',
  contact_email  STRING                 COMMENT 'Email of the primary contact at the customer.',
  contact_phone  STRING                 COMMENT 'Phone number of the primary contact at the customer.',
  annual_revenue DECIMAL(18,2)          COMMENT 'Annual revenue of the customer company in US dollars, as reported by the customer.',
  status         STRING        NOT NULL COMMENT 'Relationship status of the account: active or at_risk.'
)
COMMENT 'One row per customer account. Each account is owned by one account manager (owner_email). Unity Catalog row filters already limit every reader to the accounts they may see, so "my accounts" means all rows the reader can see. Do not add an owner_email filter.';

-- CREATE TABLE IF NOT EXISTS leaves an existing table's comment alone, so set it here too.
COMMENT ON TABLE poc.sales.customer_accounts IS 'One row per customer account. Each account is owned by one account manager (owner_email). Unity Catalog row filters already limit every reader to the accounts they may see, so "my accounts" means all rows the reader can see. Do not add an owner_email filter.';

CREATE TABLE IF NOT EXISTS poc.sales.orders (
  order_id   STRING        NOT NULL COMMENT 'Unique order identifier, for example O0001.',
  account_id STRING        NOT NULL COMMENT 'Account that placed the order. Joins to customer_accounts.account_id.',
  order_date DATE          NOT NULL COMMENT 'Date the order was placed.',
  amount     DECIMAL(18,2) NOT NULL COMMENT 'Order value in US dollars. Revenue is the sum of amount.'
)
COMMENT 'One row per order placed by a customer account. Revenue for an account in a period is the sum of amount for orders with order_date in that period.';

CREATE TABLE IF NOT EXISTS poc.support.tickets (
  ticket_id      STRING NOT NULL COMMENT 'Unique support ticket identifier, for example T0001.',
  account_id     STRING NOT NULL COMMENT 'Customer account the ticket belongs to. Joins to poc.sales.customer_accounts.account_id.',
  opened_date    DATE   NOT NULL COMMENT 'Date the ticket was opened.',
  severity       STRING NOT NULL COMMENT 'Ticket severity: low, medium, or high.',
  status         STRING NOT NULL COMMENT 'Ticket status: open or closed.',
  reporter_email STRING          COMMENT 'Email of the customer contact who reported the issue.',
  summary        STRING          COMMENT 'Short description of the issue.'
)
COMMENT 'One row per customer support ticket. Open means status = open; high severity means severity = high.';

-- Ownership lookup for the row filters and masks on orders and tickets. Databricks
-- rejects a filter or mask that reads a table which has its own filter or mask
-- (UNSUPPORTED_NESTED_ROW_OR_COLUMN_ACCESS_POLICY), so the functions read this
-- unfiltered copy of customer_accounts.owner_email. Readers get no grant on it.
CREATE TABLE IF NOT EXISTS poc.governance.account_owners (
  account_id  STRING NOT NULL COMMENT 'Account identifier. Matches poc.sales.customer_accounts.account_id.',
  owner_email STRING NOT NULL COMMENT 'Email of the account manager who owns the account.'
)
COMMENT 'Account ownership lookup used by the row filter and column mask functions. Loaded from seed/accounts.csv with the accounts.';
