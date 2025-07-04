import json
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class LLMThread(models.Model):
    _inherit = "llm.thread"

    assistant_id = fields.Many2one(
        "llm.assistant",
        string="Assistant",
        ondelete="restrict",
        help="The assistant used for this thread",
    )
    
    prompt_id = fields.Many2one(
        "llm.prompt",
        string="Prompt for workflow",
        ondelete="restrict",
        tracking=True,
        help="Prompt to use for workflow",
    )

    @api.onchange("assistant_id")
    def _onchange_assistant_id(self):
        """Update provider, model and tools when assistant changes"""
        if self.assistant_id:
            self.provider_id = self.assistant_id.provider_id
            self.model_id = self.assistant_id.model_id
            self.tool_ids = self.assistant_id.tool_ids
            self.prompt_id = self.assistant_id.prompt_id

    def set_assistant(self, assistant_id):
        """Set the assistant for this thread and update related fields

        Args:
            assistant_id (int): The ID of the assistant to set

        Returns:
            bool: True if successful, False otherwise
        """
        self.ensure_one()

        # If assistant_id is False or 0, just clear the assistant
        if not assistant_id:
            return self.write({"assistant_id": False})

        # Get the assistant record
        assistant = self.env["llm.assistant"].browse(assistant_id)
        if not assistant.exists():
            return False

        # Update the thread with the assistant and related fields
        update_vals = {
            "assistant_id": assistant_id,
            "tool_ids": [(6, 0, assistant.tool_ids.ids)],
        }
        if assistant.provider_id.id:
            update_vals["provider_id"] = assistant.provider_id.id
        if assistant.model_id.id:
            update_vals["model_id"] = assistant.model_id.id
        if assistant.prompt_id.id:
            update_vals["prompt_id"] = assistant.prompt_id.id
        return self.write(update_vals)

    def action_open_thread(self):
        """Open the thread in the chat client interface

        Returns:
            dict: Action to open the thread in the chat client
        """
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "llm_thread.chat_client_action",
            "params": {
                "default_active_id": self.id,
            },
            "context": {
                "active_id": self.id,
            },
            "target": "current",
        }

    def get_context(self, base_context=None):
        """
        Get the context to pass to prompt rendering with thread-specific enhancements.
        This is the canonical method for creating prompt context in both production and testing.

        Args:
            base_context (dict): Additional context from caller (optional)

        Returns:
            dict: Context ready for prompt rendering
        """
        context = super().get_context(base_context or {})

        # If we have an assistant with default values, add them to the context
        if self.assistant_id:
            # Get assistant's evaluated default values using the current context
            assistant_defaults = self.assistant_id.get_evaluated_default_values(context)

            # Merge assistant defaults into context
            # Assistant defaults are added first, so thread context takes precedence
            if assistant_defaults:
                context = {**assistant_defaults, **context}

        return context

    @api.model
    def get_thread_by_id(self, thread_id):
        """Get a thread record by its ID

        Args:
            thread_id (int): ID of the thread

        Returns:
            tuple: (thread, error_response)
                  If successful, error_response will be None
                  If error, thread will be None
        """
        thread = self.browse(int(thread_id))
        if not thread.exists():
            return None, {"success": False, "error": "Thread not found"}
        return thread, None

    @api.model
    def get_thread_and_assistant(self, thread_id, assistant_id=False):
        """Get thread and assistant records by their IDs

        Args:
            thread_id (int): ID of the thread
            assistant_id (int, optional): ID of the assistant, or False to clear

        Returns:
            tuple: (thread, assistant, error_response)
                  If successful, error_response will be None
                  If error, thread and/or assistant will be None
        """
        # Get thread
        thread, error = self.get_thread_by_id(thread_id)
        if error:
            return None, None, error

        # If no assistant_id, return just the thread
        if not assistant_id:
            return thread, None, None

        # Get assistant from the assistant model
        assistant, error = self.env["llm.assistant"].get_assistant_by_id(assistant_id)
        if error:
            return thread, None, error

        return thread, assistant, None

    def merge_message_lists(self, source_messages, target_messages):
        """Merge two lists of messages, handling system messages appropriately"""
        if not source_messages:
            return target_messages

        if not target_messages:
            return source_messages.copy()

        source_messages_copy = source_messages.copy()

        # Check for system messages to avoid duplicates
        system_messages_in_source = [
            msg for msg in source_messages_copy if msg.get("role") == "system"
        ]
        system_messages_in_target = [
            msg for msg in target_messages if msg.get("role") == "system"
        ]

        if system_messages_in_source and system_messages_in_target:
            # Both have system messages, merge them
            for source_msg in system_messages_in_source:
                for target_msg in system_messages_in_target:
                    source_content = self._extract_message_content(source_msg)
                    target_content = self._extract_message_content(target_msg)

                    # Merge the content
                    merged_content = f"{source_content}\n\n{target_content}"

                    # Update target message with merged content
                    if isinstance(target_msg.get("content"), list):
                        target_msg["content"][0]["text"] = merged_content
                    else:
                        target_msg["content"] = merged_content

                # Remove the source system message as we've merged it
                source_messages_copy.remove(source_msg)

        # Now add any remaining source messages at the beginning
        return source_messages_copy + target_messages

    def _extract_message_content(self, message):
        """Extract text content from a message regardless of format"""
        content = message.get("content", "")

        if isinstance(content, list) and len(content) > 0:
            return content[0].get("text", "")
        elif isinstance(content, str):
            return content
        else:
            return ""

    def get_prepend_messages(self):
        """Hook: return a list of formatted messages to prepend to the conversation."""
        self.ensure_one()

        if self.prompt_id:
            try:

                # Get messages from the prompt with enhanced context
                return self.prompt_id.get_messages(self.get_context())

            except Exception as e:
                _logger.error("Error getting messages from prompt '%s': %s", self.prompt_id.name, str(e))
                # Continue without prompt messages rather than failing completely
                self.message_post(body=f"Warning: Could not load prompt messages from '{self.prompt_id.name}': {str(e)}")

        return []

    def _process_tool_calls(self, assistant_msg):
        """Process tool calls by finding tool messages with 'requested' status."""
        self.ensure_one()
        
        # Find tool messages with 'requested' status that were created after this assistant message
        tool_messages = self.env['mail.message'].search([
            ('model', '=', self._name),
            ('res_id', '=', self.id),
            ('llm_role', '=', 'tool'),
            ('create_date', '>', assistant_msg.create_date)
        ], order='create_date ASC')
        
        # Filter for tool messages with 'requested' status
        requested_tool_messages = []
        for msg in tool_messages:
            try:
                tool_data = json.loads(msg.body)
                if tool_data.get('status') == 'requested':
                    requested_tool_messages.append(msg)
            except (json.JSONDecodeError, TypeError):
                continue
        
        if not requested_tool_messages:
            return assistant_msg
        
        # Get the tool calls max from the assistant, default to 5 if no assistant
        tool_calls_max = self.assistant_id.tool_calls_max if self.assistant_id else 5
        
        # Count recent consecutive assistant messages with tool calls to detect loops
        recent_messages = self.get_message_history_recordset(order="DESC", limit=20)
        consecutive_tool_calls = 0
        
        for msg in recent_messages:
            # Skip the current message since we're about to process it
            if msg.id == assistant_msg.id:
                continue
                
            # Check if this is an assistant message followed by tool messages
            if msg.is_llm_assistant_message():
                # Check if there are tool messages after this assistant message
                subsequent_tool_msgs = self.env['mail.message'].search([
                    ('model', '=', self._name),
                    ('res_id', '=', self.id),
                    ('llm_role', '=', 'tool'),
                    ('create_date', '>', msg.create_date)
                ], limit=1)
                
                if subsequent_tool_msgs:
                    consecutive_tool_calls += 1
                    _logger.debug(f"Thread {self.id}: Found assistant message {msg.id} with tool calls (count: {consecutive_tool_calls})")
                elif msg.body and msg.body.strip():
                    # Stop counting when we hit an assistant message with meaningful content
                    _logger.debug(f"Thread {self.id}: Hit assistant message {msg.id} with content, stopping count")
                    break
            elif msg.is_llm_user_message():
                # Stop counting when we hit a user message (new conversation turn)
                _logger.debug(f"Thread {self.id}: Hit user message {msg.id}, stopping count")
                break
        
        # Circuit breaker: if too many consecutive tool calling assistant messages, mark tools as cancelled
        if consecutive_tool_calls >= tool_calls_max:
            _logger.warning(
                f"Thread {self.id}: Circuit breaker activated! Found {consecutive_tool_calls} consecutive assistant messages with tool calls, "
                f"which exceeds the assistant's limit of {tool_calls_max}. Cancelling requested tool calls."
            )
            
            # Cancel all requested tool messages
            for tool_msg in requested_tool_messages:
                try:
                    tool_data = json.loads(tool_msg.body)
                    tool_data['status'] = 'cancelled'
                    tool_data['error'] = 'Circuit breaker activated - too many consecutive tool calls'
                    tool_msg.write({'body': json.dumps(tool_data)})
                except (json.JSONDecodeError, TypeError):
                    pass
            
            return assistant_msg
        
        # If we're under the limit, proceed with normal tool processing
        _logger.info(
            f"Thread {self.id}: Processing {len(requested_tool_messages)} tool calls ({consecutive_tool_calls}/{tool_calls_max} consecutive assistant tool call messages)"
        )
        
        # Process each tool message
        last_tool_msg = None
        for tool_msg in requested_tool_messages:
            try:
                tool_data = json.loads(tool_msg.body)
                tool_call_def = tool_data.get('tool_call')
                if tool_call_def:
                    last_tool_msg = yield from self.execute_tool_message(tool_msg, tool_call_def)
            except (json.JSONDecodeError, TypeError):
                _logger.error(f"Thread {self.id}: Invalid tool message {tool_msg.id}")
                continue
        
        return last_tool_msg or assistant_msg

    # ============================================================================
    # AI GENERATION LOGIC - Moved from llm_thread module
    # ============================================================================

    def generate(self, user_message_body, **kwargs):
        """Main generation method with actual AI intelligence."""
        self.ensure_one()
        if self.is_locked:
            raise UserError(_("This thread is already generating a response."))

        self._lock()
        try:
            # Post user message if provided
            if user_message_body:
                user_msg = self.message_post(
                    body=user_message_body,
                    llm_role='user',
                    author_id=self.env.user.partner_id.id,
                    **kwargs
                )
                self.env.cr.commit()
                yield {"type": "message_create", "message": user_msg.message_format()[0]}

            # Get last message to continue from
            last_message = self._get_last_message_from_history()

            # Continue generation loop
            while self._should_continue(last_message):
                if last_message.llm_role in ('user', 'tool'):
                    # Generate assistant response
                    last_message = yield from self._generate_assistant_response()
                elif last_message.llm_role == 'assistant':
                    # Process tool calls (check for requested tool messages)
                    last_message = yield from self._process_tool_calls(last_message)
                else:
                    break

            return last_message
        finally:
            self._unlock()

    def _generate_assistant_response(self):
        """Generate assistant response using streaming with actual AI intelligence."""
        message_history = self.get_message_history_recordset()
        chat_kwargs = {
            "messages": message_history,
            "tools": self.tool_ids,
            "stream": True,
            "prepend_messages": self.get_prepend_messages(),
        }

        stream_response = self.sudo().model_id.chat(**chat_kwargs)
        return (yield from self.message_post_from_stream(
            stream_response,
            'assistant',
            placeholder_text="Thinking..."
        ))

    def get_message_history_recordset(self, order="ASC", limit=25):
        """Get LLM messages from the thread using efficient stored field filtering.

        Args:
            order: Optional order for messages ('ASC' or 'DESC')
            limit: Optional limit on number of messages to retrieve

        Returns:
            mail.message recordset containing the LLM messages
        """
        self.ensure_one()

        # Use the stored llm_role field for efficient filtering
        domain = [
            ("model", "=", self._name),
            ("res_id", "=", self.id),
            ("llm_role", "!=", False),  # Only LLM messages
        ]

        order_clause = "create_date DESC, write_date DESC, id DESC"
        if order == "ASC":
            order_clause = "create_date ASC, write_date ASC, id ASC"

        return self.env["mail.message"].search(domain, order=order_clause, limit=limit)

    def _get_last_message_from_history(self):
        """Get the last LLM message from the message history."""
        self.ensure_one()
        result = self.get_message_history_recordset(order="DESC", limit=1)
        if not result:
            raise UserError("No LLM message found to process.")
        return result[0]

    def execute_tool_message(self, tool_msg, tool_call_def):
        """Execute a tool and update the tool message with the result."""
        fn = tool_call_def.get("function", {})
        name = fn.get("name", "unknown_tool")
        args = fn.get("arguments")

        # Update status to executing
        try:
            tool_data = json.loads(tool_msg.body)
            tool_data['status'] = 'executing'
            tool_msg.write({'body': json.dumps(tool_data)})
            yield {"type": "message_update", "message": tool_msg.message_format()[0]}
        except (json.JSONDecodeError, TypeError):
            _logger.error(f"Thread {self.id}: Invalid tool message {tool_msg.id}")
            return tool_msg

        # Execute tool and update message
        try:
            with self.env.cr.savepoint():
                result = self.with_context(message=tool_msg)._execute_tool(name, args)
                if not result:
                    raise UserError(f"No result returned from tool '{name}'")

                # Update tool data with result
                tool_data['status'] = 'completed'
                tool_data['result'] = result
                tool_msg.write({'body': json.dumps(tool_data)})
        except Exception as e:
            # Update tool data with error
            tool_data['status'] = 'error'
            tool_data['error'] = str(e)
            tool_msg.write({'body': json.dumps(tool_data)})

        yield {"type": "message_update", "message": tool_msg.message_format()[0]}
        return tool_msg

    def _should_continue(self, last_message):
        """Whether to keep looping based on the last message role and content."""
        if not last_message:
            return False

        # Use the stored llm_role field for efficient checking
        if last_message.llm_role in ('user', 'tool'):
            return True

        # Check if assistant message is followed by tool messages with 'requested' status
        if last_message.llm_role == 'assistant':
            # Look for tool messages with 'requested' status created after this assistant message
            requested_tool_msgs = self.env['mail.message'].search([
                ('model', '=', self._name),
                ('res_id', '=', self.id),
                ('llm_role', '=', 'tool'),
                ('create_date', '>', last_message.create_date)
            ])
            
            # Check if any of these tool messages have 'requested' status
            for msg in requested_tool_msgs:
                try:
                    tool_data = json.loads(msg.body)
                    if tool_data.get('status') == 'requested':
                        return True
                except (json.JSONDecodeError, TypeError):
                    continue

        return False

    def _execute_tool(self, tool_name, arguments_str):
        """Execute a tool and return the result."""
        self.ensure_one()
        tool = self.tool_ids.filtered(lambda t: t.name == tool_name)[:1]
        if not tool:
            raise UserError(f"Tool '{tool_name}' not found in this thread")
        arguments = json.loads(arguments_str)
        return tool.execute(arguments)


