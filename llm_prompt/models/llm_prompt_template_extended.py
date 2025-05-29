import json
import logging
import re

from jinja2 import Environment

from odoo import models

_logger = logging.getLogger(__name__)


class LLMPromptTemplate(models.Model):
    _inherit = "llm.prompt.template"

    def _substitute_placeholders(self, content, arguments):
        """
        Replace argument placeholders in content with their values using Jinja2.
        Extends the base implementation to handle special cases:
        1. When arg_name is 'related_record', fetch from llm.thread.get_related_record()
        2. When placeholder is like {{record.field_name}}, get the field value from the record

        Args:
            content (str): Content with placeholders
            arguments (dict): Dictionary of argument values

        Returns:
            str: Content with placeholders replaced by values
        """
        
        
        # Process boolean values for JSON compatibility
        processed_args = dict(arguments)
        for arg_name, arg_value in arguments.items():
            if isinstance(arg_value, bool):
                # Convert Python True/False to JSON true/false
                processed_args[arg_name] = "true" if arg_value else "false"
        
        # Check if we need to handle related record
        related_record_pattern = r'\{\{(\s*)related_record(\s*)\}\}'
        record_field_pattern = r'\{\{(\s*)related_record\.([a-zA-Z0-9_]+)(\s*)\}\}'
        
        if re.search(related_record_pattern, content) or re.search(record_field_pattern, content):
            # Get the related record
            thread = self.env['llm.thread'].get_thread_from_context()
            if thread:
                related_record = thread.get_related_record()
                if related_record:
                    # Add related_record to the context
                    processed_args['related_record'] = json.dumps({
                        "model": related_record._name,
                        "id": related_record.id,
                        "display_name": related_record.display_name
                    })
                    
                    # Create a custom function to access record fields
                    def get_record_field(field_name):
                        if hasattr(related_record, field_name):
                            try:
                                field_value = getattr(related_record, field_name)
                                # Convert to string with proper JSON handling
                                if isinstance(field_value, bool):
                                    return "true" if field_value else "false"
                                return str(field_value)
                            except Exception as e:
                                _logger.error("Error getting field %s from record: %s", field_name, str(e))
                                return f"ERROR: {str(e)}"
                        else:
                            _logger.warning("Record doesn't have field: %s", field_name)
                            return f"FIELD_NOT_FOUND: {field_name}"
                    
                    # Create Jinja2 environment with custom functions
                    env = Environment(
                        variable_start_string="{{",
                        variable_end_string="}}",
                        trim_blocks=True,
                        lstrip_blocks=True,
                    )
                    
                    # Register the custom function
                    env.globals['get_record_field'] = get_record_field
                    
                    # Preprocess the template to replace {{related_record.field_name}} with {{get_record_field('field_name')}}
                    processed_content = re.sub(
                        r'\{\{(\s*)related_record\.([a-zA-Z0-9_]+)(\s*)\}\}',
                        r'{{ get_record_field("\2") }}',
                        content
                    )
                    
                    # Create and render the template
                    template = env.from_string(processed_content)
                    return template.render(**processed_args)
                else:
                    _logger.warning("No related record found for thread %s", thread.id)
            else:
                _logger.info("No thread found in context")
        
        # If no related record handling needed, use the parent implementation
        return super()._substitute_placeholders(content, processed_args)