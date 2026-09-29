# C Task 3：REAL04/05 工具与 MCP

Work from E:\eval-platform. No commit. No eval_platform.db.

Use tests.followup_helpers.stats_service context manager (random port).

real04_tools(client, stats_base_url) register HTTP parse+stats via resources API (reuse A wizard/manifest shapes from followup_helpers.tool_manifest). Invoke parse with 3 inputs; one invalid expecting failed. Return resource ids and correlation ids.

real05_mcp(client, stats_base_url) register or probe MCP at {stats_base_url}/mcp. tools/call success and empty args failed.

Look at POST /api/resources/register and invoke and mcp/probe. Do not invent endpoints.

Tests start stats_service subprocess. unittest tests.test_real_fill -v
Report .superpowers/sdd/task-c3-report.md
