import json
import logging

from odoo import api, fields, models

from odoo.addons.llm_mail_message_subtypes.const import (
    LLM_ASSISTANT_SUBTYPE_XMLID,
)

_logger = logging.getLogger(__name__)


class LLMThread(models.Model):
    _inherit = "llm.thread"

    prompt_id = fields.Many2one(
        "llm.prompt",
        string="Prompt for workflow",
        ondelete="restrict",
        tracking=True,
        help="Prompt to use for workflow",
    )

    def _next_step(self, last_message):
        """Dispatch to the next generator based on message type."""
        if last_message.is_llm_user_media_gen_message():
            return self._get_media_gen_response(last_message)
        return super()._next_step(last_message)

    def _get_media_gen_response(self, user_message):
        self.ensure_one()

        generation_inputs = user_message.generation_inputs
        user_message_body = user_message.body
        stream_response = self.model_id.generate_media(
            json.loads(generation_inputs), stream=True
        )

        assistant_msg = yield from self.env[
            "mail.message"
        ].create_message_from_media_gen_stream(
            self,
            stream_response,
            LLM_ASSISTANT_SUBTYPE_XMLID,
            placeholder_text=f'<em>"{user_message_body}"</em>',
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
        **kwargs,
    ):
        base_vals = super().build_update_vals(
            subtype_xmlid,
            tool_call_id=tool_call_id,
            tool_calls=tool_calls,
            tool_call_definition=tool_call_definition,
            tool_call_result=tool_call_result,
        )
        if base_vals:
            return base_vals
        generation_inputs = kwargs.get("generation_inputs")
        attachment_ids = kwargs.get("attachment_ids")
        vals = {
            "generation_inputs": generation_inputs,
            "attachment_ids": attachment_ids,
        }
        return {k: v for k, v in vals.items() if v is not None}

    @api.model
    def process_prompt_substitutions(self, thread_id, generation_inputs):
        thread = self.browse(thread_id)
        if not thread or not thread.prompt_id:
            return generation_inputs
        return thread.prompt_id.get_formatted_prompt(default_values=generation_inputs)
        