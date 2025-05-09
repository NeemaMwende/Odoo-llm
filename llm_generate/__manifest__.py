{
    "name": "LLM Media Generation",
    "version": "1.0",
    "category": "Productivity/Discuss",
    "summary": "Media generation capabilities for LLM models",
    "description": """
        Adds support for generating images, audio, and other media using LLM models.
    """,
    "depends": [
        "llm",
        "llm_thread",
        "llm_mail_message_subtypes",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/llm_generation_config_views.xml",
        "views/llm_model_views.xml",
        "views/llm_menu_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "llm_generate/static/src/components/llm_media_form/llm_media_form.js",
            "llm_generate/static/src/components/llm_media_form/llm_media_form.xml",
            "llm_generate/static/src/models/composer.js",
            "llm_generate/static/src/models/llm_model.js"
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}