import functools
import json
import logging

import emoji
import markdown2

from odoo import _, api, fields, models
from odoo.exceptions import UserError

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


class RelatedRecordProxy:
    """
    A proxy object that provides clean access to related record fields in Jinja templates.
    Usage in templates: {{ related_record.get_field('field_name', 'default_value') }}
    When called directly, returns JSON with model name, id, and display name.
    """

    def __init__(self, record):
        self._record = record

    def get_field(self, field_name, default=""):
        """
        Get a field value from the related record.

        Args:
            field_name (str): The field name to access
            default: Default value if field doesn't exist or is empty

        Returns:
            The field value, or default if not available
        """
        if not self._record:
            return default

        try:
            if hasattr(self._record, field_name):
                value = getattr(self._record, field_name)

                # Handle different field types
                if value is None:
                    return default
                elif isinstance(value, bool):
                    return value  # Keep as boolean for Jinja
                elif hasattr(value, 'name'):  # Many2one field
                    return value.name
                elif hasattr(value, 'mapped'):  # Many2many/One2many field
                    return value.mapped('name')
                else:
                    return value
            else:
                _logger.debug("Field '%s' not found on record %s", field_name, self._record)
                return default

        except Exception as e:
            _logger.error("Error getting field '%s' from record: %s", field_name, str(e))
            return default

    def __getattr__(self, name):
        """Allow direct attribute access as fallback"""
        return self.get_field(name)

    def __bool__(self):
        """Return True if we have a record"""
        return bool(self._record)

    def __str__(self):
        """When called by itself, return JSON of model name, id, and display name"""
        if not self._record:
            return json.dumps({
                "model": None,
                "id": None,
                "display_name": None
            })

        return json.dumps({
            "model": self._record._name,
            "id": self._record.id,
            "display_name": getattr(self._record, 'display_name', str(self._record))
        })

    def __repr__(self):
        """Same as __str__ for consistency"""
        return self.__str__()


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
    def message_post(self, *, llm_role=None, tool_name=None, tool_call_id=None, message_type='comment',
                     tool_calls=None, tool_call_definition=None, tool_call_result=None,
                     **kwargs):
        """Override to handle LLM-specific message types and metadata.
        
        Args:
            llm_role (str): The LLM role ('user', 'assistant', 'tool', 'system')
                           If provided, will automatically set the appropriate subtype
            tool_name (str): Name of the tool (for tool messages)
            tool_call_id (str): ID of the tool call
            tool_calls (str): JSON string of tool calls
            tool_call_definition (str): JSON string of tool call definition
            tool_call_result (str): JSON string of tool call result
        """

        # Convert LLM role to subtype_xmlid if provided
        if llm_role:
            _, role_to_id = self.env['mail.message'].get_llm_roles()
            if llm_role in role_to_id:
                # Get the xmlid from the role
                subtype_xmlid = f"llm.mt_{llm_role}"
                kwargs['subtype_xmlid'] = subtype_xmlid

        # Handle LLM-specific subtypes and email_from generation
        if not kwargs.get('author_id') and not kwargs.get('email_from'):
            kwargs['email_from'] = self._get_llm_email_from(
                kwargs.get('subtype_xmlid'), kwargs.get('author_id'), tool_name
            )

        # Convert markdown to HTML if needed
        if kwargs.get('body'):
            kwargs['body'] = self._process_llm_body(kwargs['body'])

        # Create the message using standard mail.thread flow
        message = super().message_post(message_type=message_type, **kwargs)

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

        if subtype_xmlid == 'llm.mt_tool':
            name = tool_name or "Tool"
            return f"{name} <tool@{provider_name.lower().replace(' ', '')}.ai>"
        elif subtype_xmlid == 'llm.mt_assistant':
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

    def message_post_from_stream(self, stream, llm_role, placeholder_text="…", **kwargs):
        """Create and update a message from a streaming response.
        
        Args:
            stream: Generator yielding chunks of response data
            llm_role (str): The LLM role ('user', 'assistant', 'tool', 'system')
            placeholder_text (str): Text to show while streaming
        """
        message = None
        accumulated_content = ""
        accumulated_calls = []

        for chunk in stream:
            if message is None and (chunk.get("content") or chunk.get("tool_calls")):
                # Create initial message with placeholder
                message = self.message_post(
                    body=placeholder_text,
                    llm_role=llm_role,
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
            llm_role='tool',
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
    # GENERATION FLOW - Refactored to use message_post with roles
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
                elif (last_message.llm_role == 'assistant' and
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
            'assistant',
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
    # HELPER METHODS - Optimized with stored llm_role field
    # ============================================================================

    def get_message_history_recordset(self, order="ASC", limit=None):
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
        if not last_message:
            return False

        # Use the stored llm_role field for efficient checking
        if last_message.llm_role in ('user', 'tool'):
            return True

        if last_message.llm_role == 'assistant' and last_message.tool_calls:
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
        context = {
            **(base_context or {}),
            'thread_id': self.id,
        }

        try:
            related_record = self.env[self.model].browse(self.res_id)
            if related_record:
                context['related_record'] = RelatedRecordProxy(related_record)
                context['related_model'] = self.model
                context['related_res_id'] = self.res_id
            else:
                context['related_record'] = None
                context['related_model'] = None
                context['related_res_id'] = None
        except Exception as e:
            _logger.warning("Error accessing related record %s,%s: %s", self.model, self.res_id, e)

        return context
