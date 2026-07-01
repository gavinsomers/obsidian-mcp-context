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
    assert "list_vault_entity_types" in tools
    assert "get_vault_entity_timeline" in tools
    assert "get_vault_entity_context" in tools
    assert "list_vault_entity_events" in tools
    assert "list_vault_entity_relationships" in tools
    assert "list_vault_entity_states" in tools
    assert "list_vault_entity_open_loops" in tools
    assert "list_vault_context_presets" in tools
    assert "get_vault_context_preset" in tools
    assert "search_vault_agent_context" in tools
    assert "get_vault_project_context" in tools
    assert "get_vault_person_context" in tools
    assert "list_vault_open_loops" in tools
    assert "list_vault_decisions" in tools
    assert "list_vault_risks" in tools


def test_mcp_parser_accepts_http_host_and_port():
    parser = mcp_server.build_parser()
    args = parser.parse_args(
        [
            "--transport",
            "streamable-http",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--vault-profile",
            "generated-demo",
        ]
    )

    assert args.transport == "streamable-http"
    assert args.host == "0.0.0.0"
    assert args.port == 8000
    assert args.vault_profile == "generated-demo"
