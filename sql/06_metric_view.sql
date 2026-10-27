-- Metric view: revenue by account and quarter, for the Sales Genie space.
-- Run as admin:  uv run tools/run_sql.py --profile admin sql/06_metric_view.sql
--
-- The row filters and masks on orders and customer_accounts apply to the reader,
-- so an account manager gets their own accounts with NULL revenue (orders.amount is
-- Confidential) and finance_analysts get every account with revenue.

CREATE OR REPLACE VIEW poc.sales.revenue_by_account
WITH METRICS LANGUAGE YAML
COMMENT 'Revenue (sum of order amount) and order count by account, region, and quarter.'
AS $$
version: 1.1
comment: "Revenue (sum of order amount) and order count by account, region, and quarter."
source: poc.sales.orders
joins:
  - name: account
    source: poc.sales.customer_accounts
    'on': source.account_id = account.account_id
    rely:
      at_most_one_match: true
dimensions:
  - name: account_id
    expr: source.account_id
    comment: "Unique account identifier, for example A001."
  - name: account_name
    expr: account.account_name
    comment: "Name of the customer company."
  - name: region
    expr: account.region
    comment: "Sales region of the account: East or West."
  - name: owner_email
    expr: account.owner_email
    comment: "Email of the account manager who owns the account."
  - name: order_quarter
    expr: DATE_TRUNC('QUARTER', source.order_date)
    comment: "First day of the calendar quarter of the order. Q3 2026 is 2026-07-01."
  - name: order_quarter_label
    expr: concat(year(source.order_date), '-Q', quarter(source.order_date))
    comment: "Calendar quarter of the order as text, for example 2026-Q3."
measures:
  - name: revenue
    expr: SUM(source.amount)
    comment: "Revenue in US dollars: the sum of order amount."
  - name: order_count
    expr: COUNT(1)
    comment: "Number of orders."
$$;

GRANT SELECT ON TABLE poc.sales.revenue_by_account TO `account_managers`;
GRANT SELECT ON TABLE poc.sales.revenue_by_account TO `finance_analysts`;
