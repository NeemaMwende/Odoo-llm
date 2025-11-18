{
    "name": "LLM Invoice Assistant",
    "summary": "AI-powered invoice analysis assistant with OCR document parsing",
    "description": """
        Intelligent invoice assistant that helps analyze vendor bills and invoices using AI.
        Features document parsing with OCR, automated data extraction, and smart invoice validation.
    """,
    "category": "Accounting/AI",
    "version": "18.0.1.0.0",
    "depends": [
        "account",  # Invoice model (account.move)
        "llm_assistant",  # Includes llm, llm_thread, llm_tool
        "llm_mistral_ocr",  # OCR tool
    ],
    "author": "Apexive Solutions LLC",
    "website": "https://github.com/apexive/odoo-llm",
    "data": [
        "data/llm_assistant_data.xml",
        "views/account_move_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "llm_assistant_account_invoice/static/src/js/assistant_button_helper.js",
        ],
    },
    "license": "LGPL-3",
    "installable": True,
    "application": False,
    "auto_install": False,
}
