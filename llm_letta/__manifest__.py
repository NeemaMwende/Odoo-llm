{
    "name": "Letta LLM Integration",
    "summary": "Letta provider integration for LLM module",
    "description": """
        Implements Letta provider service for the LLM integration module.
        Supports model fetching from Letta platform for stateful AI agents.

        Note: This initial implementation only supports model fetching.
        Chat, embedding, and generation features are not yet implemented.
    """,
    "author": "Apexive Solutions LLC",
    "website": "https://github.com/apexive/odoo-llm",
    "category": "Technical",
    "version": "18.0.1.0.0",
    "depends": ["llm", "llm_thread", "llm_assistant", "llm_mcp_server"],
    "external_dependencies": {
        "python": ["letta-client"],
    },
    "data": [
        "data/llm_publisher.xml",
        "data/llm_provider.xml",
        "views/llm_provider_views.xml",
        "views/llm_thread_views.xml",
    ],
    "images": [
        "static/description/banner.jpeg",
    ],
    "license": "LGPL-3",
    "installable": True,
}
