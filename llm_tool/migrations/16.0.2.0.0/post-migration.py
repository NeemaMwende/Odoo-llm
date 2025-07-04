import json
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Migration script to convert existing tool messages from separate fields to JSON body format.
    
    This migration:
    1. Finds all messages with tool-related fields
    2. Converts the field data to JSON format in the body
    3. Removes the old field data (handled by ORM when fields are removed)
    """
    _logger.info("Starting migration to convert tool messages to JSON body format")
    
    # Find all tool messages that have tool_call_id (these need conversion)
    cr.execute("""
        SELECT id, tool_call_id, tool_call_definition, tool_call_result, body, llm_role
        FROM mail_message 
        WHERE tool_call_id IS NOT NULL
        ORDER BY id
    """)
    
    tool_messages = cr.fetchall()
    _logger.info(f"Found {len(tool_messages)} tool messages to migrate")
    
    converted_count = 0
    error_count = 0
    
    for msg_id, tool_call_id, tool_call_definition, tool_call_result, body, llm_role in tool_messages:
        try:
            # Create new tool data structure
            tool_data = {
                "type": "tool_execution",
                "tool_call_id": tool_call_id,
            }
            
            # Parse and add tool call definition
            if tool_call_definition:
                try:
                    tool_call = json.loads(tool_call_definition)
                    tool_data["tool_call"] = tool_call
                    # Extract tool name from definition
                    if isinstance(tool_call, dict) and "function" in tool_call:
                        function = tool_call["function"]
                        if isinstance(function, dict) and "name" in function:
                            tool_data["tool_name"] = function["name"]
                except json.JSONDecodeError:
                    _logger.warning(f"Failed to parse tool_call_definition for message {msg_id}")
                    tool_data["tool_name"] = "unknown_tool"
            else:
                tool_data["tool_name"] = "unknown_tool"
            
            # Parse and add tool call result
            if tool_call_result:
                try:
                    result = json.loads(tool_call_result)
                    if isinstance(result, dict) and "error" in result:
                        tool_data["status"] = "error"
                        tool_data["error"] = result["error"]
                    else:
                        tool_data["status"] = "completed"
                        tool_data["result"] = result
                except json.JSONDecodeError:
                    # If result is not valid JSON, treat as plain text result
                    tool_data["status"] = "completed"
                    tool_data["result"] = tool_call_result
            else:
                # No result means it's still executing or failed without result
                tool_data["status"] = "executing"
            
            # Convert tool data to JSON string for body
            new_body = json.dumps(tool_data)
            
            # Update the message body
            cr.execute("""
                UPDATE mail_message 
                SET body = %s 
                WHERE id = %s
            """, (new_body, msg_id))
            
            converted_count += 1
            
            if converted_count % 100 == 0:
                _logger.info(f"Converted {converted_count} tool messages...")
                
        except Exception as e:
            error_count += 1
            _logger.error(f"Error converting tool message {msg_id}: {str(e)}")
            continue
    
    _logger.info(f"Migration completed: {converted_count} messages converted, {error_count} errors")
    
    # Also migrate assistant messages that have tool_calls field
    cr.execute("""
        SELECT id, tool_calls, body
        FROM mail_message 
        WHERE tool_calls IS NOT NULL AND llm_role = 'assistant'
        ORDER BY id
    """)
    
    assistant_messages = cr.fetchall()
    _logger.info(f"Found {len(assistant_messages)} assistant messages with tool_calls")
    
    # These don't need body conversion, but we should validate the tool_calls JSON
    validated_count = 0
    for msg_id, tool_calls, body in assistant_messages:
        try:
            # Validate that tool_calls is valid JSON
            json.loads(tool_calls)
            validated_count += 1
        except json.JSONDecodeError:
            _logger.warning(f"Assistant message {msg_id} has invalid tool_calls JSON, clearing it")
            cr.execute("UPDATE mail_message SET tool_calls = NULL WHERE id = %s", (msg_id,))
    
    _logger.info(f"Validated {validated_count} assistant messages with tool_calls")
