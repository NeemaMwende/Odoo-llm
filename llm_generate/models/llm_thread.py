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
        if self.prompt_id and hasattr(self.prompt_id, 'input_schema_json'):
            return self._ensure_dict(self.prompt_id.input_schema_json)
        elif self.model_id and self.model_id.details:
            return self._ensure_dict(self.model_id.details.get('input_schema'))
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
        if not schema.get('properties'):
            return context
            
        return {k: v for k, v in context.items() 
                if k in schema['properties'] and v is not None}

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

    def handle_generation_message(self, message):
        """Handle a user message with generation data in body_json."""
        self.ensure_one()
        
        if not message.body_json:
            return
            
        try:
            # Prepare final inputs
            final_inputs = self.prepare_generation_inputs(message.body_json)
            
            # Generate using model
            result = self.model_id.generate(final_inputs)
            
            # Handle streaming or direct response
            if hasattr(result, '__iter__') and not isinstance(result, (str, dict)):
                # Streaming response
                for chunk in result:
                    if chunk.get("content"):
                        self._create_generation_result_message(chunk["content"])
                        break
            else:
                # Direct response
                self._create_generation_result_message(result)
                
        except Exception as e:
            _logger.error(f"Error in generation: {e}")
            self.message_post(
                body=f"Generation failed: {str(e)}",
                llm_role='assistant'
            )

    def _create_generation_result_message(self, content):
        """Create a message with generation result."""
        self.ensure_one()
        
        # Format content for display
        if isinstance(content, list):
            # Handle multiple results (e.g., image URLs)
            formatted_content = []
            for i, item in enumerate(content):
                if isinstance(item, str) and item.startswith(('http://', 'https://')):
                    formatted_content.append(f"![Generated Image {i+1}]({item})")
                else:
                    formatted_content.append(str(item))
            body = "\n".join(formatted_content)
        else:
            body = str(content)
        
        # Create assistant message
        return self.message_post(
            body=body,
            llm_role='assistant',
            body_json={"generation_result": content}
        )

    @api.model
    def get_model_generation_io_by_id(self, model_id):
        """Get model generation I/O schema by ID."""
        try:
            model = self.env['llm.model'].browse(int(model_id))
            if not model.exists():
                return {"error": f"Model {model_id} not found"}
                
            return {
                "input_schema": model.details.get('input_schema') if model.details else None,
                "output_schema": model.details.get('output_schema') if model.details else None,
                "model_id": model.id,
                "model_name": model.name,
            }
        except Exception as e:
            return {"error": str(e)}
