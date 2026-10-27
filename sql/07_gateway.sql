-- Unity Gateway access to Genie One. Only the two business groups may call the
-- MCP service system.ai.genie_one_mcp. Every other identity is refused at the
-- gateway before Genie writes any SQL.
-- Run as frank, a member of metastore_admins (the metastore admin group):
--   uv run tools/run_sql.py --profile frank sql/07_gateway.sql
--
-- Databricks-provided MCP services inherit EXECUTE from the system.ai schema,
-- which every account user holds by default. MANAGE on system.ai lets the
-- metastore admins change grants on the services in it; the REVOKE removes the
-- default. The REVOKE also removes EXECUTE on the other system.ai MCP services
-- and functions, which this POC does not use.
--
-- Undo:
--   GRANT EXECUTE ON SCHEMA system.ai TO `account users`;

GRANT MANAGE ON SCHEMA system.ai TO `metastore_admins`;

GRANT EXECUTE ON MCP SERVICE system.ai.genie_one_mcp TO `account_managers`;
GRANT EXECUTE ON MCP SERVICE system.ai.genie_one_mcp TO `finance_analysts`;

REVOKE EXECUTE ON SCHEMA system.ai FROM `account users`;
