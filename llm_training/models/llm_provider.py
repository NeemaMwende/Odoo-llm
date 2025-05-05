import logging

from odoo import models

_logger = logging.getLogger(__name__)


class LLMProvider(models.Model):
    _inherit = "llm.provider"

    def openai_upload_file(self, file_tuple, purpose="fine-tune"):
        """Upload a file to OpenAI"""
        response = self.client.files.create(file=file_tuple, purpose=purpose)
        return response
        

    def upload_file(self, file_tuple, purpose="fine-tune"):
        """Upload a file to the provider"""
        return self._dispatch("upload_file", file_tuple, purpose)