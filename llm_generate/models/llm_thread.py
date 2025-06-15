# Add these methods to your existing models/llm_thread.py

import json
import logging
import re
from odoo import api, models
from odoo.addons.llm_prompt.utils import render_template

_logger = logging.getLogger(__name__)


class LLMThread(models.Model):
    _inherit = "llm.thread"

    @api.model
    def get_rendered_prompt_defaults(self, thread_id, assistant_id=None):
        """Get rendered prompt defaults for a specific thread and optional assistant.
        
        Args:
            thread_id (int): ID of the thread
            assistant_id (int, optional): ID of the assistant to use instead of thread's assistant
            
        Returns:
            dict: Rendered default values for the prompt template
        """
        thread, error = self.get_thread_by_id(thread_id)
        if error:
            return {}

        # Use provided assistant_id or thread's assistant
        assistant = None
        if assistant_id:
            assistant = self.env['llm.assistant'].browse(assistant_id)
            if not assistant.exists():
                _logger.warning(f"Assistant {assistant_id} not found")
                return {}
        elif thread.assistant_id:
            assistant = thread.assistant_id

        # If no assistant or assistant has no prompt, try thread's direct prompt
        prompt = None
        if assistant and assistant.prompt_id:
            prompt = assistant.prompt_id
        elif thread.prompt_id:
            prompt = thread.prompt_id

        if not prompt:
            return {}

        try:
            # Get thread context (which includes assistant defaults and related record context)
            context = thread.get_context()

            # Render template and extract defaults
            rendered_defaults = self._render_prompt_template_defaults(prompt, context)

            _logger.debug(f"Rendered defaults for thread {thread_id}: {rendered_defaults}")
            return rendered_defaults

        except Exception as e:
            _logger.error(f"Error rendering prompt defaults for thread {thread_id}: {e}")
            return {}

    @api.model
    def render_template_for_json(self, thread_id, prompt_id=None, current_values=None):
        """Render template specifically for JSON editor display.

        Args:
            thread_id (int): Thread ID for context
            prompt_id (int, optional): Specific prompt ID to use
            current_values (dict, optional): Current form values to merge

        Returns:
            dict: Rendered template values ready for JSON editor
        """
        thread, error = self.get_thread_by_id(thread_id)
        if error:
            return current_values or {}

        # Determine which prompt to use
        prompt = None
        if prompt_id:
            prompt = self.env['llm.prompt'].browse(prompt_id)
            if not prompt.exists():
                _logger.warning(f"Prompt {prompt_id} not found")
                return current_values or {}
        elif thread.assistant_id and thread.assistant_id.prompt_id:
            prompt = thread.assistant_id.prompt_id
        elif thread.prompt_id:
            prompt = thread.prompt_id

        if not prompt:
            return current_values or {}

        try:
            # Get thread context
            context = thread.get_context()

            # Get the base rendered defaults
            rendered_defaults = self._render_prompt_template_defaults(prompt, context)

            # If we have current values, merge them (current values take precedence)
            if current_values:
                rendered_defaults.update(current_values)

            _logger.debug(f"Rendered template for JSON for thread {thread_id}: {rendered_defaults}")
            return rendered_defaults

        except Exception as e:
            _logger.error(f"Error rendering template for JSON for thread {thread_id}: {e}")
            return current_values or {}

    @api.model
    def render_generation_json(self, thread_id, generation_inputs, without_prompt_template=False):
        """Combine generation inputs with rendered prompt template values.

        Args:
            thread_id (int): Thread ID for context
            generation_inputs (dict): Raw generation inputs from form
            without_prompt_template (bool): Skip prompt template rendering if True

        Returns:
            dict: Combined generation inputs with template values
        """
        if without_prompt_template:
            return generation_inputs

        thread, error = self.get_thread_by_id(thread_id)
        if error:
            return generation_inputs

        try:
            # Get rendered template defaults
            template_defaults = self.get_rendered_prompt_defaults(thread_id)

            # Merge template defaults with generation inputs
            # Generation inputs take precedence over template defaults
            if template_defaults:
                combined_inputs = {**template_defaults, **generation_inputs}
                _logger.debug(f"Combined generation inputs for thread {thread_id}: {combined_inputs}")
                return combined_inputs
            else:
                return generation_inputs

        except Exception as e:
            _logger.error(f"Error combining generation inputs for thread {thread_id}: {e}")
            return generation_inputs

    def _render_prompt_template_defaults(self, prompt, context):
        """Render prompt template and extract default values for form fields.

        Args:
            prompt (llm.prompt): The prompt record to render
            context (dict): Context for template rendering (from thread.get_context())

        Returns:
            dict: Default values extracted from rendered template
        """
        if not prompt or not prompt.template:
            return {}

        try:
            # Use the prompt's utility to render the template with context
            rendered_template = render_template(template=prompt.template, context=context)

            # Extract defaults from the rendered content
            defaults = self._extract_defaults_from_rendered_template(rendered_template, prompt, context)

            # Also include any schema defaults from the prompt's input_schema_json
            if hasattr(prompt, 'input_schema_json') and prompt.input_schema_json:
                schema_defaults = self._extract_schema_defaults(prompt.input_schema_json)
                # Template extracted defaults take precedence over schema defaults
                combined_defaults = {**schema_defaults, **defaults}
                return combined_defaults

            return defaults

        except Exception as e:
            _logger.error(f"Error rendering template defaults for prompt {prompt.id}: {e}")
            return {}

    def _extract_defaults_from_rendered_template(self, rendered_template, prompt, context):
        """Extract default values from rendered template content.

        This method parses the rendered template and extracts default values
        for form fields. Customize this based on your template format.

        Args:
            rendered_template (str): The rendered template content
            prompt (llm.prompt): The prompt record
            context (dict): Template context

        Returns:
            dict: Default values for form fields
        """
        defaults = {}

        if not rendered_template:
            return defaults

        try:
            # Method 1: Extract from template structure/comments
            defaults.update(self._extract_from_template_structure(rendered_template))

            # Method 2: Extract from template content patterns
            defaults.update(self._extract_from_content_patterns(rendered_template))

            # Method 3: Extract from context if it contains generation defaults
            # The thread's get_context() already includes assistant defaults
            generation_defaults = {k: v for k, v in context.items()
                                   if k in ['prompt', 'style', 'quality', 'size', 'model', 'negative_prompt']}
            if generation_defaults:
                defaults.update(generation_defaults)

        except Exception as e:
            _logger.error(f"Error extracting defaults from rendered template: {e}")

        return defaults

    def _extract_schema_defaults(self, input_schema_json):
        """Extract default values from prompt's input schema.

        Args:
            input_schema_json (dict): The prompt's input schema

        Returns:
            dict: Default values from schema
        """
        defaults = {}

        try:
            schema = input_schema_json if isinstance(input_schema_json, dict) else json.loads(input_schema_json)

            if schema and 'properties' in schema:
                for field_name, field_def in schema['properties'].items():
                    if 'default' in field_def:
                        defaults[field_name] = field_def['default']

        except (json.JSONDecodeError, TypeError) as e:
            _logger.debug(f"Could not parse prompt schema for defaults: {e}")

        return defaults

    def _extract_from_template_structure(self, rendered_template):
        """Extract defaults from template structure/comments.

        Looks for patterns like:
        <!-- DEFAULT: field_name = value -->
        # DEFAULT: field_name = value

        Args:
            rendered_template (str): Rendered template content

        Returns:
            dict: Extracted defaults
        """
        defaults = {}

        # Look for HTML comment defaults
        html_pattern = r'<!--\s*DEFAULT:\s*(\w+)\s*=\s*(.+?)\s*-->'
        for match in re.finditer(html_pattern, rendered_template, re.IGNORECASE):
            field_name = match.group(1).strip()
            field_value = match.group(2).strip().strip('"\'')
            defaults[field_name] = field_value

        # Look for hash comment defaults
        hash_pattern = r'#\s*DEFAULT:\s*(\w+)\s*=\s*(.+?)(?:\n|$)'
        for match in re.finditer(hash_pattern, rendered_template, re.IGNORECASE):
            field_name = match.group(1).strip()
            field_value = match.group(2).strip().strip('"\'')
            defaults[field_name] = field_value

        return defaults

    def _extract_from_content_patterns(self, rendered_template):
        """Extract defaults from common content patterns.

        Looks for patterns like:
        prompt: Generate an image of...
        style: photographic
        quality: hd

        Args:
            rendered_template (str): Rendered template content

        Returns:
            dict: Extracted defaults
        """
        defaults = {}

        # Common field patterns - customize based on your templates
        patterns = {
            'prompt': [
                r'prompt:\s*([^\n]+)',
                r'description:\s*([^\n]+)',
                r'generate:\s*([^\n]+)',
            ],
            'negative_prompt': [
                r'negative_prompt:\s*([^\n]+)',
                r'avoid:\s*([^\n]+)',
                r'exclude:\s*([^\n]+)',
            ],
            'style': [
                r'style:\s*([^\n]+)',
                r'art_style:\s*([^\n]+)',
            ],
            'quality': [
                r'quality:\s*([^\n]+)',
                r'resolution:\s*([^\n]+)',
            ],
            'size': [
                r'size:\s*([^\n]+)',
                r'dimensions:\s*([^\n]+)',
            ],
            'model': [
                r'model:\s*([^\n]+)',
                r'version:\s*([^\n]+)',
            ],
        }

        for field_name, field_patterns in patterns.items():
            for pattern in field_patterns:
                match = re.search(pattern, rendered_template, re.IGNORECASE)
                if match:
                    value = match.group(1).strip().strip('"\'')
                    if value and field_name not in defaults:
                        defaults[field_name] = value
                        break  # Use first match for this field

        return defaults

    @api.model
    def get_model_generation_io_by_id(self, model_id):
        """Get model generation input/output schema by model ID.

        This method provides a centralized way to get model schema information
        for the frontend, following the existing pattern.

        Args:
            model_id (int): ID of the llm.model

        Returns:
            dict: Model schema information
        """
        try:
            model = self.env['llm.model'].browse(int(model_id))
            if not model.exists():
                raise ValueError(f"Model {model_id} not found")

            return {
                "input_schema": model.input_schema,
                "output_schema": model.output_schema,
                "model_id": model.id,
                "model_name": model.name,
                "model_use": model.model_use,
                "is_media_generation": model._is_media_generation_model(),
            }
        except Exception as e:
            _logger.error(f"Error getting model schema for {model_id}: {e}")
            return {
                "error": str(e),
                "input_schema": None,
                "output_schema": None,
                "model_id": None,
                "model_name": None,
            }

    @api.model
    def refresh_assistant_defaults(self, thread_id, assistant_id=None):
        """Refresh assistant's evaluated default values for a thread.

        This is useful when you want to force a refresh of the assistant's
        defaults after context changes.

        Args:
            thread_id (int): ID of the thread
            assistant_id (int, optional): Specific assistant ID

        Returns:
            dict: Refreshed default values
        """
        thread, error = self.get_thread_by_id(thread_id)
        if error:
            return {}

        assistant = None
        if assistant_id:
            assistant = self.env['llm.assistant'].browse(assistant_id)
        elif thread.assistant_id:
            assistant = thread.assistant_id

        if not assistant or not assistant.exists():
            return {}

        try:
            # Get fresh context
            context = thread.get_context()

            # Force refresh of assistant's evaluated defaults
            if hasattr(assistant, 'refresh_evaluated_defaults'):
                assistant.refresh_evaluated_defaults(context)

            # Get the refreshed defaults
            defaults = assistant.get_evaluated_default_values(context)

            return defaults or {}

        except Exception as e:
            _logger.error(f"Error refreshing assistant defaults for thread {thread_id}: {e}")
            return {}
