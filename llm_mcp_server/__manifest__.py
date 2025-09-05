{
    "name": "LLM MCP Server",
    "version": "18.0.1.0.0",
    "category": "Technical",
    "summary": "Model Context Protocol (MCP) server for exposing LLM tools",
    "description": """
        Model Context Protocol (MCP) Server for Odoo LLM

        This module exposes Odoo LLM tools as an MCP server, allowing external systems
        like Claude Desktop, Letta, or other MCP clients to access and execute Odoo tools.

        Key features:
        - HTTP-based MCP server implementation
        - JSON-RPC 2.0 protocol support
        - Automatic tool discovery from llm.tool records
        - Tool execution with proper context handling
        - Compatible with streamable_http transport
    """,
    "author": "Apexive Solutions LLC",
    "website": "https://github.com/apexive/odoo-llm",
    "license": "LGPL-3",
    "depends": ["base", "llm", "llm_tool"],
    "data": [
        "security/ir.model.access.csv",
        "data/llm_mcp_server_config.xml",
        "views/llm_mcp_server_config_views.xml",
    ],
    "images": [
        "static/description/banner.jpeg",
    ],
    "auto_install": False,
    "application": False,
    "installable": True,
}
