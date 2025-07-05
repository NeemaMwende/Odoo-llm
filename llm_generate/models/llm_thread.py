import json
import logging

from odoo import api, models

from odoo.addons.llm_assistant.utils import render_template

_logger = logging.getLogger(__name__)


class LLMThread(models.Model):
    _inherit = "llm.thread"

    def get_input_schema(self):
        """Get input schema for generation forms."""
        self.ensure_one()

        # Try prompt schema first, then model schema
        if self.prompt_id and hasattr(self.prompt_id, "input_schema_json"):
            return self._ensure_dict(self.prompt_id.input_schema_json)
        elif self.model_id and self.model_id.details:
            return self._ensure_dict(self.model_id.details.get("input_schema"))
        return {}

    def _ensure_dict(self, value):
        """Convert value to dict if it's a JSON string."""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return {}
        return {}

    def get_form_defaults(self):
        """Get default values for generation form from context."""
        self.ensure_one()
        context = self.get_context()
        schema = self.get_input_schema()

        # Filter context to only include schema properties
        if not schema.get("properties"):
            return context

        return {
            k: v
            for k, v in context.items()
            if k in schema["properties"] and v is not None
        }

    def prepare_generation_inputs(self, inputs):
        """Prepare final inputs for generation.

        Args:
            inputs (dict): Raw inputs from form

        Returns:
            dict: Final inputs ready for model generation
        """
        self.ensure_one()

        # Merge context with inputs
        context = self.get_context()
        merged_inputs = {**context, **inputs}

        # If no prompt, return merged inputs
        if not self.prompt_id:
            return merged_inputs

        # Render prompt with merged inputs
        try:
            rendered = render_template(self.prompt_id.template, merged_inputs)
            return json.loads(rendered)
        except Exception as e:
            _logger.error(f"Error rendering prompt: {e}")
            return merged_inputs

    def _generate_response(self, message):
        """Handle a user message with generation data in body_json."""
        self.ensure_one()

        if not message.body_json:
            return

        try:
            # Prepare final inputs
            final_inputs = self.prepare_generation_inputs(message.body_json)

            # Generate using model - now returns tuple (output_data, urls)
            output_data, urls = self.model_id.generate(final_inputs)

            # Process URLs and create attachments
            attachments = self._process_generation_urls(urls)

            # Generate markdown content
            markdown_content = self._generate_markdown_from_urls(urls)

            # Create assistant message with processed content
            self._create_generation_result_message(
                markdown_content, output_data, attachments
            )

        except Exception as e:
            _logger.error(f"Error in generation: {e}")
            self.message_post(body=f"Generation failed: {str(e)}", llm_role="assistant")

    def _process_generation_urls(self, urls):
        """Process URLs and create attachment records"""
        attachments = []
        for url_data in urls:
            attachment = self._create_url_attachment(url_data)
            if attachment:
                attachments.append(attachment)
        return attachments

    def _create_url_attachment(self, url_data):
        """Create attachment record for URL"""
        attachment = self.env['ir.attachment'].create({
            'name': url_data.get('filename', 'generated_content'),
            'type': 'url',
            'url': url_data['url'],
            'mimetype': url_data.get('content_type', 'application/octet-stream'),
            'res_model': 'mail.message',
            'res_id': 0,  # Will be updated when message is created
        })
        return attachment

    def _generate_markdown_from_urls(self, urls):
        """Generate markdown content from URLs"""
        markdown_parts = []
        for i, url_data in enumerate(urls):
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
        
        return "\n\n".join(markdown_parts)

    def _create_generation_result_message(self, markdown_content, output_data, attachments):
        """Create message with generation results"""
        message = self.message_post(
            body=markdown_content,
            llm_role="assistant",
            body_json=output_data,
            attachment_ids=[att.id for att in attachments]
        )
        
        # Update attachment res_id
        for attachment in attachments:
            attachment.res_id = message.id
        
        return message

    @api.model
    def get_model_generation_io_by_id(self, model_id):
        """Get model generation I/O schema by ID."""
        try:
            model = self.env["llm.model"].browse(int(model_id))
            if not model.exists():
                return {"error": f"Model {model_id} not found"}

            return {
                "input_schema": model.details.get("input_schema")
                if model.details
                else None,
                "output_schema": model.details.get("output_schema")
                if model.details
                else None,
                "model_id": model.id,
                "model_name": model.name,
            }
        except Exception as e:
            return {"error": str(e)}
