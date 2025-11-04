18.0.1.4.0 (2025-10-23)
~~~~~~~~~~~~~~~~~~~~~~~

* [MIGRATION] Migrated to Odoo 18.0
* [IMP] Updated views and manifest for compatibility

16.0.1.3.0
~~~~~~~~~~

* [BREAKING] Moved message subtypes to base module
* [ADD] Added required `llm_role` field computation with automatic migration
* [IMP] Enhanced provider dispatch mechanism
* [MIGRATION] Automatic computation of `llm_role` for existing messages
* [MIGRATION] Database migration creates indexes for performance

16.0.1.1.0 (2025-03-06)
~~~~~~~~~~~~~~~~~~~~~~~

* [ADD] Tool support framework in base LLM models
* [IMP] Enhanced provider interface to support tool execution
* [IMP] Updated model handling for function calling capabilities

16.0.1.0.0 (2025-01-02)
~~~~~~~~~~~~~~~~~~~~~~~

* [INIT] Initial release
