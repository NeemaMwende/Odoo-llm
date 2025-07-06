import logging

from odoo import models

_logger = logging.getLogger(__name__)


class LLMGenerationMixin(models.AbstractModel):
    _name = 'llm.generation.mixin'
    _description = 'Shared generation utilities'

    def process_generation_urls(self, urls, message=None):
        """Process URLs and create attachments, return markdown content.
        
        Args:
            urls: List of URL data from model.generate()
            message: Optional message record to attach files to
            
        Returns:
            tuple: (markdown_content, attachments)
        """
        attachments = []
        markdown_parts = []

        for i, url_data in enumerate(urls):
            # Create attachment if message provided
            if message:
                attachment = self._create_url_attachment(url_data, message.id)
                if attachment:
                    attachments.append(attachment)
            
            # Generate markdown
            content_type = url_data.get('content_type', '')
            url = url_data['url']
            
            if content_type.startswith('image/'):
                markdown_parts.append(f"![Generated Image {i+1}]({url})")
            elif content_type.startswith('video/'):
                markdown_parts.append(f"[Generated Video {i+1}]({url})")
            elif content_type.startswith('audio/'):
                markdown_parts.append(f"[Generated Audio {i+1}]({url})")
            else:
                markdown_parts.append(f"[Generated Content {i+1}]({url})")

        return "\n\n".join(markdown_parts), attachments

    def _create_url_attachment(self, url_data, message_id):
        """Create attachment record for URL"""
        return self.env['ir.attachment'].create({
            'name': url_data.get('filename', 'generated_content'),
            'type': 'url',
            'url': url_data['url'],
            'mimetype': url_data.get('content_type', 'application/octet-stream'),
            'res_model': 'mail.message',
            'res_id': message_id,
        })
