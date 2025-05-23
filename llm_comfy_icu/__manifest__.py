{
    "name": "LLM ComfyICU Integration",
    "version": "16.0.1.0.0",
    "category": "Productivity/LLM",
    "summary": "Integration with ComfyICU API for media generation",
    "description": """
        This module integrates Odoo with ComfyICU API for media generation.
        It provides a new provider type that can be used with the LLM framework.
    """,
    "author": "Fleek",
    "website": "https://fleek.works",
    "license": "LGPL-3",
    "depends": [
        "llm",
        "llm_generate",
    ],
    "images": [
        "static/description/banner.png",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
