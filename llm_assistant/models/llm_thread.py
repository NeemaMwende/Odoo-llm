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

    # NOTE: _process_tool_calls method removed - we now use the simpler approach
    # where tool messages are created one at a time and processed by the main loop
    # This eliminates the complexity of searching for and batching tool messages

    # ============================================================================
    # AI GENERATION LOGIC - Refactored to use mail.message methods
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
                if last_message.llm_role == 'user':
                    # Generate assistant response
                    last_message = yield from self._generate_assistant_response()
                elif last_message.llm_role == 'tool' and last_message.is_tool_message_with_status('requested'):
                    # Execute the tool directly - much simpler than complex searching!
                    last_message = yield from last_message.execute_tool_call(thread_model=self)
                else:
                    break

            return last_message
        finally:
            self._unlock()

    def _generate_assistant_response(self):
        """Generate assistant response and handle tool calls."""
        message_history = self.get_message_history_recordset()
        
        # Determine if we should use streaming
        use_streaming = getattr(self.model_id, 'supports_streaming', True)
        
        chat_kwargs = {
            "messages": message_history,
            "tools": self.tool_ids,
            "stream": use_streaming,
            "prepend_messages": self.get_prepend_messages(),
        }
        if use_streaming:
            # Handle streaming response - process tool calls directly from stream
            stream_response = self.sudo().model_id.chat(**chat_kwargs)
            assistant_message = yield from self._handle_streaming_response(stream_response)
        else:
            # Handle non-streaming response
            response = self.sudo().model_id.chat(**chat_kwargs)
            assistant_message = yield from self._handle_non_streaming_response(response)
        
        return assistant_message

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

    def _should_continue(self, last_message):
        """Whether to keep looping based on the last message role and content."""
        if not last_message or last_message.llm_role == 'assistant':
            return False
        return True

    def _handle_streaming_response(self, stream_response):
        """Handle streaming response from LLM provider with tool call processing."""
        message = None
        accumulated_content = ""
        collected_tool_calls = []

        for chunk in stream_response:
            # Initialize message on first content
            if message is None and chunk.get("content"):
                message = self.message_post(
                    body="Thinking...",
                    llm_role='assistant',
                    author_id=False
                )
                yield {"type": "message_create", "message": message.message_format()[0]}

            # Handle content streaming
            if chunk.get("content"):
                accumulated_content += chunk["content"]
                message.write({"body": self._process_llm_body(accumulated_content)})
                yield {"type": "message_chunk", "message": message.message_format()[0]}

            # Collect tool calls for processing
            if chunk.get("tool_calls"):
                collected_tool_calls.extend(chunk["tool_calls"])
                _logger.debug(f"Collected {len(chunk['tool_calls'])} tool calls from chunk")

            # Handle errors
            if chunk.get("error"):
                yield {"type": "error", "error": chunk["error"]}
                return message

        # Final update for assistant message
        if message and accumulated_content:
            message.write({"body": self._process_llm_body(accumulated_content)})
            yield {"type": "message_update", "message": message.message_format()[0]}

        # Process tool calls if present using the new method
        if collected_tool_calls:
            _logger.info(f"Thread {self.id}: Processing {len(collected_tool_calls)} tool calls")
            tool_message = yield from self._create_tool_messages(collected_tool_calls)
            # Return the tool message as the last message so the main loop can process it
            return tool_message if tool_message else message

        return message

    def _handle_non_streaming_response(self, response):
        """Handle non-streaming response from LLM provider."""
        # Extract content and tool calls from response
        content = response.get("content", "")
        tool_calls = response.get("tool_calls", [])
        
        if not content and not tool_calls:
            content = "No response from model"
        
        # Create assistant message
        assistant_message = self.message_post(
            body=self._process_llm_body(content) if content else "",
            llm_role='assistant',
            author_id=False
        )
        
        yield {"type": "message_create", "message": assistant_message.message_format()[0]}
        
        # Process tool calls if present using the new method
        if tool_calls:
            _logger.info(f"Thread {self.id}: Processing {len(tool_calls)} tool calls")
            tool_message = yield from self._create_tool_messages(tool_calls)
            # Return the tool message as the last message so the main loop can process it
            return tool_message if tool_message else assistant_message
        
        return assistant_message

    def _create_tool_messages(self, tool_calls):
        """Create tool messages from tool calls data using the new mail.message method.
        
        NOTE: This method currently creates only the FIRST tool call and returns it.
        This simplifies the execution flow - the returned tool message becomes the 
        last_message and gets processed by the main generation loop.
        
        TODO: In the future, we may want to handle multiple tool calls at once,
        but for now this single-tool approach keeps the logic simple and clear.
        """
        if not tool_calls:
            _logger.debug("No tool calls to process")
            return None
        
        if not isinstance(tool_calls, list):
            _logger.error(f"Tool calls is not a list: {type(tool_calls)}")
            return None
        
        # For now, only process the first tool call to keep things simple
        # The main generation loop will handle it and then process any remaining ones
        tool_call = tool_calls[0]
        
        if len(tool_calls) > 1:
            _logger.info(f"Thread {self.id}: Multiple tool calls received ({len(tool_calls)}), processing first one only")
        
        try:
            # Use the new post_tool_call method from mail.message
            tool_msg = self.env['mail.message'].post_tool_call(tool_call, thread_model=self)
            yield {"type": "message_create", "message": tool_msg.message_format()[0]}
            return tool_msg
            
        except Exception as e:
            _logger.error(f"Error creating tool message: {e}")
            
            # Create error tool message using the new method
            try:
                error_msg = self.env['mail.message'].create_tool_error_message(
                    tool_call, str(e), thread_model=self
                )
                yield {"type": "message_create", "message": error_msg.message_format()[0]}
                return error_msg
            except Exception as e2:
                _logger.error(f"Failed to create error message: {e2}")
                return None
