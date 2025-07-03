import functools
import json
import logging

import emoji
import markdown2

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from odoo.addons.llm_mail_message_subtypes.const import (
    LLM_ASSISTANT_SUBTYPE_XMLID,
    LLM_TOOL_RESULT_SUBTYPE_XMLID,
    LLM_USER_SUBTYPE_XMLID,
)

_logger = logging.getLogger(__name__)


def execute_with_new_cursor(func_to_decorate):
    """Decorator to execute a method within a new, immediately committed cursor context.

    It injects the browsed record from the new environment as the first argument
    after 'self'. Assumes the decorated method is called on a singleton recordset.
    """

    @functools.wraps(func_to_decorate)
    def wrapper(self, *args, **kwargs):
        self.ensure_one()
        with self.pool.cursor() as cr:
            env = api.Environment(cr, self.env.uid, self.env.context)
            record_in_new_env = env[self._name].browse(self.ids)
            return func_to_decorate(self, record_in_new_env, *args, **kwargs)

    return wrapper


class LLMThread(models.Model):
    _name = "llm.thread"
    _description = "LLM Chat Thread"
    _inherit = ["mail.thread"]
    _order = "write_date DESC"

    name = fields.Char(
        string="Title",
        required=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="User",
        default=lambda self: self.env.user,
        required=True,
        ondelete="restrict",
    )
    provider_id = fields.Many2one(
        "llm.provider",
        string="Provider",
        required=True,
        ondelete="restrict",
    )
    model_id = fields.Many2one(
        "llm.model",
        string="Model",
        required=True,
        domain="[('provider_id', '=', provider_id), ('model_use', 'in', ['chat', 'multimodal'])]",
        ondelete="restrict",
    )
    active = fields.Boolean(default=True)

    # Updated fields for related record reference
    model = fields.Char(
        string="Related Document Model",
        help="Technical name of the related model"
    )
    res_id = fields.Many2oneReference(
        string="Related Document ID",
        model_field="model",
        help="ID of the related record"
    )

    is_locked = fields.Boolean(
        string="Locked, Preventing Concurrent Generation",
        default=False,
        copy=False,
        help="Indicates if the thread is currently locked to prevent concurrent generation.",
    )

    tool_ids = fields.Many2many(
        "llm.tool",
        string="Available Tools",
        help="Tools that can be used by the LLM in this thread",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Set default title if not provided"""
        for vals in vals_list:
            if not vals.get("name"):
                vals["name"] = f"Chat with {self.model_id.name}"
        return super().create(vals_list)

    # ============================================================================
    # MESSAGE POST OVERRIDES - Clean integration with mail.thread
    # ============================================================================

    @api.returns('mail.message', lambda value: value.id)
    def message_post(self, *, subtype_xmlid=None, tool_name=None, tool_call_id=None, message_type='comment',
                     tool_calls=None, tool_call_definition=None, tool_call_result=None, 
                     **kwargs):
        """Override to handle LLM-specific message types and metadata."""
        
        # Handle LLM-specific subtypes and email_from generation
        if not kwargs.get('author_id') and not kwargs.get('email_from'):
            kwargs['email_from'] = self._get_llm_email_from(
                subtype_xmlid, kwargs.get('author_id'), tool_name
            )
        
        # Convert markdown to HTML if needed
        if kwargs.get('body'):
            kwargs['body'] = self._process_llm_body(kwargs['body'])

        # Create the message using standard mail.thread flow
        message = super().message_post(subtype_xmlid=subtype_xmlid, message_type=message_type, **kwargs)

        # Add LLM-specific fields after creation
        llm_fields = {}
        if tool_calls:
            llm_fields['tool_calls'] = tool_calls
        if tool_call_id:
            llm_fields.update({
                'tool_call_id': tool_call_id,
                'tool_call_definition': tool_call_definition,
                'tool_call_result': tool_call_result,
            })
        
        if llm_fields:
            message.write(llm_fields)
        
        return message

    def _get_llm_email_from(self, subtype_xmlid, author_id, tool_name=None):
        """Generate appropriate email_from for LLM messages."""
        if author_id:
            return None  # Let standard flow handle it
            
        provider_name = self.provider_id.name
        model_name = self.model_id.name
        
        if subtype_xmlid == LLM_TOOL_RESULT_SUBTYPE_XMLID:
            name = tool_name or "Tool"
            return f"{name} <tool@{provider_name.lower().replace(' ', '')}.ai>"
        elif subtype_xmlid == LLM_ASSISTANT_SUBTYPE_XMLID:
            return f"{model_name} <ai@{provider_name.lower().replace(' ', '')}.ai>"
        
        return None

    def _process_llm_body(self, body):
        """Process body content for LLM messages (markdown to HTML conversion)."""
        if not body:
            return body
        return markdown2.markdown(emoji.demojize(body))

    # ============================================================================
    # STREAMING MESSAGE CREATION
    # ============================================================================

    def message_post_from_stream(self, stream, subtype_xmlid, placeholder_text="…", **kwargs):
        """Create and update a message from a streaming response."""
        message = None
        accumulated_content = ""
        accumulated_calls = []
        
        for chunk in stream:
            if message is None and (chunk.get("content") or chunk.get("tool_calls")):
                # Create initial message with placeholder
                message = self.message_post(
                    body=placeholder_text,
                    subtype_xmlid=subtype_xmlid,
                    author_id=False,
                    **kwargs
                )
                yield {"type": "message_create", "message": message.message_format()[0]}
            
            if chunk.get("content"):
                accumulated_content += chunk["content"]
                message.write({"body": self._process_llm_body(accumulated_content)})
                yield {"type": "message_chunk", "message": message.message_format()[0]}
            
            if chunk.get("tool_calls"):
                valid_calls = [c for c in chunk["tool_calls"] 
                              if isinstance(c, dict) and c.get("id")]
                accumulated_calls.extend(valid_calls)
                message.write({"tool_calls": json.dumps(accumulated_calls)})
                yield {"type": "message_update", "message": message.message_format()[0]}
            
            if chunk.get("error"):
                yield {"type": "error", "error": chunk["error"]}
                return message
        
        # Final update
        if message:
            final_updates = {}
            if accumulated_content:
                final_updates["body"] = self._process_llm_body(accumulated_content)
            if accumulated_calls:
                final_updates["tool_calls"] = json.dumps(accumulated_calls)
            
            if final_updates:
                message.write(final_updates)
            yield {"type": "message_update", "message": message.message_format()[0]}
        
        return message

    def message_post_tool_result(self, tool_call_def, **kwargs):
        """Post a tool result message using standard message_post flow."""
        call_id = tool_call_def.get("id")
        fn = tool_call_def.get("function", {})
        name = fn.get("name", "unknown_tool")
        args = fn.get("arguments")
        
        # Create placeholder message
        message = self.message_post(
            body=f"Executing: {name}…",
            subtype_xmlid=LLM_TOOL_RESULT_SUBTYPE_XMLID,
            author_id=False,
            tool_call_id=call_id,
            tool_call_definition=json.dumps(tool_call_def),
            tool_name=name,
            **kwargs
        )
        yield {"type": "message_create", "message": message.message_format()[0]}
        
        # Execute tool and update message
        try:
            with self.env.cr.savepoint():
                result = self.with_context(message=message)._execute_tool(name, args)
                if not result:
                    raise UserError(f"No result returned from tool '{name}'")
                
                # Update message with result
                message.write({
                    "tool_call_result": json.dumps(result),
                    "body": f"Result for {name}"
                })
        except Exception as e:
            message.write({
                "tool_call_result": json.dumps({"error": str(e)}),
                "body": f"Error executing {name}"
            })
        
        yield {"type": "message_update", "message": message.message_format()[0]}
        return message

    # ============================================================================
    # GENERATION FLOW - Refactored to use message_post
    # ============================================================================

    def generate(self, user_message_body, **kwargs):
        """Main generation method using standard message_post flow."""
        self.ensure_one()
        if self.is_locked:
            raise UserError(_("This thread is already generating a response."))
        
        self._lock()
        try:
            # Post user message if provided
            if user_message_body:
                user_msg = self.message_post(
                    body=user_message_body,
                    subtype_xmlid=LLM_USER_SUBTYPE_XMLID,
                    author_id=self.env.user.partner_id.id,
                    **kwargs
                )
                self.env.cr.commit()
                yield {"type": "message_create", "message": user_msg.message_format()[0]}
            
            # Get last message to continue from
            last_message = self._get_last_message_from_history()
            
            # Continue generation loop
            while self._should_continue(last_message):
                if (last_message.is_llm_user_message() or 
                    last_message.is_llm_tool_result_message()):
                    # Generate assistant response
                    last_message = yield from self._generate_assistant_response()
                elif (last_message.is_llm_assistant_message() and 
                      last_message.tool_calls):
                    # Process tool calls
                    last_message = yield from self._process_tool_calls(last_message)
                else:
                    break
            
            return last_message
        finally:
            self._unlock()

    def _generate_assistant_response(self):
        """Generate assistant response using streaming."""
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
            LLM_ASSISTANT_SUBTYPE_XMLID,
            placeholder_text="Thinking..."
        ))

    def _process_tool_calls(self, assistant_msg):
        """Process tool calls from assistant message."""
        self.ensure_one()
        defs = json.loads(assistant_msg.tool_calls or "[]")
        last_tool_msg = None
        for tool_def in defs:
            last_tool_msg = yield from self.message_post_tool_result(tool_def)
        return last_tool_msg

    # ============================================================================
    # HELPER METHODS
    # ============================================================================

    def get_message_history_recordset(self, order="ASC", limit=None):
        """Get messages from the thread

        Args:
            order: Optional order for messages ('ASC' or 'DESC')
            limit: Optional limit on number of messages to retrieve

        Returns:
            mail.message recordset containing the messages
        """
        self.ensure_one()
        subtypes_to_fetch = [
            self.env.ref(LLM_USER_SUBTYPE_XMLID, raise_if_not_found=True),
            self.env.ref(LLM_ASSISTANT_SUBTYPE_XMLID, raise_if_not_found=True),
            self.env.ref(LLM_TOOL_RESULT_SUBTYPE_XMLID, raise_if_not_found=True),
        ]
        subtype_ids = [st.id for st in subtypes_to_fetch if st]

        # Default to descending order to get the most recent messages
        order_clause = "create_date DESC, write_date DESC, id DESC"
        domain = [
            ("model", "=", self._name),
            ("res_id", "=", self.id),
            ("subtype_id", "in", subtype_ids),
        ]
        # Fetch messages (most recent first)
        messages = self.env["mail.message"].search(
            domain, order=order_clause, limit=limit
        )

        if order == "ASC":
            messages = messages[::-1]
        return messages

    def _get_last_message_from_history(self):
        """Get the last message from the message history."""
        self.ensure_one()
        last_message = None
        result = self.get_message_history_recordset(order="DESC", limit=1)
        if result:
            last_message = result[0]
        if not last_message:
            raise UserError("No message found to process.")
        return last_message

    def _should_continue(self, last_message):
        """Whether to keep looping on the last_message."""
        if not last_message:
            return False
        if (last_message.is_llm_user_message() or 
            last_message.is_llm_tool_result_message()):
            return True
        if last_message.is_llm_assistant_message() and last_message.tool_calls:
            return True
        return False

    def get_prepend_messages(self):
        """Hook: return a list of formatted messages to prepend to the conversation.
        Override in other modules if needed.

        Returns:
            list: List of message dictionaries in the format:
                [{"role": "system", "content": "..."},
                 {"role": "user", "content": "..."},
                 ...]
        """
        return []

    def _execute_tool(self, tool_name, arguments_str):
        """Execute a tool and return the result."""
        self.ensure_one()
        tool = self.tool_ids.filtered(lambda t: t.name == tool_name)[:1]
        if not tool:
            raise UserError(f"Tool '{tool_name}' not found in this thread")
        arguments = json.loads(arguments_str)
        return tool.execute(arguments)

    # ============================================================================
    # LOCKING MECHANISM
    # ============================================================================

    def _lock(self):
        """Acquires a lock on the thread, ensuring immediate commit."""
        self.ensure_one()
        if self._read_is_locked_decorated():
            raise UserError(
                _("Lock Error: This thread is already generating a response. Please wait.")
            )
        self._write_vals_decorated({"is_locked": True})

    def _unlock(self):
        """Releases the lock on the thread, ensuring immediate commit."""
        self.ensure_one()
        if self._read_is_locked_decorated():
            self._write_vals_decorated({"is_locked": False})

    @execute_with_new_cursor
    def _read_is_locked_decorated(self, record_in_new_env):
        """Reads the 'is_locked' status using a new cursor."""
        return record_in_new_env.is_locked

    @execute_with_new_cursor
    def _write_vals_decorated(self, record_in_new_env, vals):
        """Writes values using a new, immediately committed cursor."""
        return record_in_new_env.write(vals)

    # ============================================================================
    # ODOO HOOKS AND CLEANUP
    # ============================================================================

    @api.ondelete(at_uninstall=False)
    def _unlink_llm_thread(self):
        unlink_ids = [record.id for record in self]
        self.env["bus.bus"]._sendone(
            self.env.user.partner_id, "llm.thread/delete", {"ids": unlink_ids}
        )

    def get_context(self, base_context=None):
        return base_context or {}
