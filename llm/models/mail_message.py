from odoo import models, tools

class MailMessage(models.Model):
    """Extension of mail.message to handle LLM-specific message subtypes."""

    _inherit = "mail.message"

    LLM_XMLIDS = (
        'llm.mt_tool',
        'llm.mt_user',
        'llm.mt_assistant',
        'llm.mt_system',
    )

    @tools.ormcache('xmlid', 'model')
    def _get_subtype_id_for_xmlid(self, xmlid, model='mail.message.subtype'):
        """Resolve and cache a single XML ID to subtype record ID."""
        return self.env['ir.model.data']._xmlid_to_res_id(xmlid, raise_if_not_found=False) or False

    def is_llm_message(self):
        """Check if messages are LLM messages."""
        llm_subtype_ids = set(
            self._get_subtype_id_for_xmlid(xmlid)
            for xmlid in self.LLM_XMLIDS
            if self._get_subtype_id_for_xmlid(xmlid)
        )
        return {
            message: bool(message.subtype_id and message.subtype_id.id in llm_subtype_ids)
            for message in self
        }

    def is_llm_user_message(self):
        """Check if messages are LLM user messages."""
        return self._check_llm_subtype('llm.mt_user')

    def is_llm_assistant_message(self):
        """Check if messages are LLM assistant messages."""
        return self._check_llm_subtype('llm.mt_assistant')

    def is_llm_tool_message(self):
        """Check if messages are LLM tool messages."""
        return self._check_llm_subtype('llm.mt_tool')

    def is_llm_system_message(self):
        """Check if messages are LLM system messages."""
        return self._check_llm_subtype('llm.mt_system')

    def _check_llm_subtype(self, xmlid):
        """Check if messages match a specific LLM subtype."""
        target_subtype_id = self._get_subtype_id_for_xmlid(xmlid)
        return {
            message: bool(message.subtype_id and message.subtype_id.id == target_subtype_id)
            for message in self
        }
