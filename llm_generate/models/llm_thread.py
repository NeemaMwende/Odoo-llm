import json
import logging

from odoo import _, api, models
from odoo.exceptions import UserError

from odoo.addons.llm_mail_message_subtypes.const import (
    LLM_ASSISTANT_SUBTYPE_XMLID,
    LLM_TOOL_RESULT_SUBTYPE_XMLID,
    LLM_USER_SUBTYPE_XMLID,
)

_logger = logging.getLogger(__name__)

class LLMThread(models.Model):
    _inherit = "llm.thread"

    def _post_message(self, **kwargs):
        self.ensure_one()
        # if subtype_xmlid is not provided or wrong,message_post automatically
        # uses the default subtype
        subtype_xmlid = kwargs.get("subtype_xmlid")
        author_id = kwargs.get("author_id")
        body = kwargs.get("body", "")
        email_from = self.get_email_from(
            self.provider_id.name,
            self.model_id.name,
            subtype_xmlid,
            author_id,
            kwargs.get("tool_name"),
        )
        post_vals = self.build_post_vals(
            subtype_xmlid, body, author_id, email_from
        )
        message = self.message_post(**post_vals)
        extra_vals = self.build_update_vals(
            subtype_xmlid,
            tool_call_id=kwargs.get("tool_call_id"),
            tool_calls=kwargs.get("tool_calls"),
            tool_call_definition=kwargs.get("tool_call_definition"),
            tool_call_result=kwargs.get("tool_call_result"),
            generation_inputs=kwargs.get("generation_inputs"),
            attachment_ids=kwargs.get("attachment_ids"),
        )
        if extra_vals:
            message.write(extra_vals)
        return message

    def _init_message(self, user_message_body, generation_inputs=None):
        """Initialize first message: user input or history."""
        if user_message_body or generation_inputs:
            return self._post_message(
                subtype_xmlid=LLM_USER_SUBTYPE_XMLID,
                body=user_message_body,
                author_id=self.env.user.partner_id.id,
                generation_inputs=generation_inputs,
            )
        return self._get_last_message_from_history()

    def _next_step(self, last_message):
        """Dispatch to the next generator based on message type."""
        if last_message.is_llm_user_media_gen_message():
            return self._get_media_gen_response(last_message)
        return super()._next_step(last_message)

    def generate(self, user_message_body, generation_inputs=None):
        self.ensure_one()
        if self.is_locked:
            raise UserError(
                _("This thread is already generating a response. Please wait.")
            )
        self._lock()

        try:
            # orchestrate via hooks
            last = self._init_message(user_message_body, generation_inputs)
            if user_message_body:
                yield {"type": "message_create", "message": last.message_format()[0]}
            while self._should_continue(last):
                last = yield from self._next_step(last)
            return last
        finally:
            self._unlock()

    def _get_media_gen_response(self, user_message):
        self.ensure_one()
        
        generation_inputs = user_message.generation_inputs
        user_message_body = user_message.body
        stream_response = self.model_id.generate_media(json.loads(generation_inputs), stream=True)
        
        assistant_msg = yield from self.env["mail.message"].create_message_from_media_gen_stream(
            self,
            stream_response,
            LLM_ASSISTANT_SUBTYPE_XMLID,
            placeholder_text=f"<strong>Generated media for:</strong>\n{user_message_body}",
        )
        return assistant_msg

    @api.model
    def build_update_vals(
        self,
        subtype_xmlid,
        tool_call_id=None,
        tool_calls=None,
        tool_call_definition=None,
        tool_call_result=None,
        generation_inputs=None,
        attachment_ids=None,
    ):
        if subtype_xmlid == LLM_ASSISTANT_SUBTYPE_XMLID and tool_calls:
            return {"tool_calls": tool_calls}
        if subtype_xmlid == LLM_TOOL_RESULT_SUBTYPE_XMLID:
            vals = {
                "tool_call_id": tool_call_id,
                "tool_call_definition": tool_call_definition,
                "tool_call_result": tool_call_result,
            }
        else:
            vals = {
                "generation_inputs": generation_inputs,
                "attachment_ids": attachment_ids,
            }
        
        return {k: v for k, v in vals.items() if v is not None}

