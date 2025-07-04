16.0.2.0.0 (2025-07-03)
~~~~~~~~~~~~~~~~~~~~~~~

* [BREAKING] Refactored tool message storage to use JSON in message body instead of separate fields
* [REMOVE] Removed tool_calls, tool_call_id, tool_call_definition, tool_call_result fields from mail.message
* [IMP] Simplified tool message structure - all tool data now stored as JSON in message body
* [IMP] Added display_body computed field for human-readable tool message content
* [IMP] Updated provider message formatting to parse tool data from JSON body
* [IMP] Enhanced frontend to handle new JSON-based tool message structure
* [IMP] Updated message validation to work with new tool message format
* [MIGRATION] Added migration script to convert existing tool messages to new JSON format
* [PERF] Reduced database storage overhead by eliminating duplicate tool data fields
* [MAINT] Cleaner architecture with single source of truth for tool data

16.0.1.0.1 (2025-04-08)
~~~~~~~~~~~~~~~~~~~~~~~

* [IMP] Improvements:
  * Added explicit type hints (`list[str]`, `list[list[Any]]`) to list fields in Pydantic models for `fields_inspector`, `record_unlinker`, and `record_updater` tools to improve schema validation and API compatibility.

16.0.1.0.0 (2025-03-06)
~~~~~~~~~~~~~~~~~~~~~~~

* [INIT] Initial release of the module with the following features:
  * LLM Tool Integration - Added ability to chat with LLM models using llm.tool implementations
  * Tool Implementations - Support for odoo_record_retriever and odoo_server_action tools
  * Tool Message Handling - Chat UI for tool messages with cog icon and display of tool arguments and results
