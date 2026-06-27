from obsidian_mcp_context import mcp_server


def test_bounded_limit_caps_tool_results():
    assert mcp_server._bounded_limit(0) == 1
    assert mcp_server._bounded_limit(25) == 25
    assert mcp_server._bounded_limit(999) == mcp_server.MAX_LIMIT


def test_mcp_server_exposes_generic_obsidian_tools():
    tools = mcp_server.mcp._tool_manager._tools

    assert "list_vault_notes" in tools
    assert "search_vault_blocks" in tools
    assert "list_vault_tasks" in tools
    assert "get_vault_note_context" in tools
    assert "get_vault_warehouse_summary" in tools
    assert "list_vault_entities" in tools
    assert "get_vault_entity_timeline" in tools
    assert "search_vault_agent_context" in tools
