import json
import logging
import re

from odoo import models

_logger = logging.getLogger(__name__)


class LLMPromptTemplate(models.Model):
    _inherit = "llm.prompt.template"

    def _substitute_placeholders(self, content, arguments):
        """
        Replace argument placeholders in content with their values.
        Extends the base implementation to handle special cases:
        1. When arg_name is 'related_record', fetch from llm.thread.get_related_record()
        2. When placeholder is like {{record.field_name}}, get the field value from the record

        Args:
            content (str): Content with placeholders
            arguments (dict): Dictionary of argument values

        Returns:
            str: Content with placeholders replaced by values
        """
        related_record = None
        
        related_record_pattern = r'\{\{(\s*)related_record(\s*)\}\}'
        record_field_pattern = r'\{\{(\s*)related_record\.([a-zA-Z0-9_]+)(\s*)\}\}'
        
        if re.search(related_record_pattern, content) or re.search(record_field_pattern, content):
            thread = self.env['llm.thread'].get_thread_from_context()
            if thread:
                related_record = thread.get_related_record()
                if related_record:
                    # Replace {{related_record}} placeholders with a JSON representation
                    matches = re.finditer(related_record_pattern, content)
                    replacements = []
                    
                    for match in matches:
                        full_match = match.group(0)
                        # Create a simple JSON with the basic record info
                        record_json = json.dumps({
                            "model": related_record._name,
                            "id": related_record.id,
                            "display_name": related_record.display_name
                        })
                        replacements.append((full_match, record_json))
                    
                    # Apply replacements for related_record
                    result = content
                    for old, new in replacements:
                        result = result.replace(old, new)
                    
                    # Now handle record.field_name placeholders
                    matches = re.finditer(record_field_pattern, result)
                    replacements = []
                    
                    for match in matches:
                        full_match = match.group(0)
                        field_name = match.group(2)
                        
                        if hasattr(related_record, field_name):
                            try:
                                field_value = getattr(related_record, field_name)
                                
                                # Convert to string
                                if isinstance(field_value, bool):
                                    str_value = "true" if field_value else "false"
                                else:
                                    str_value = str(field_value)
                                
                                replacements.append((full_match, str_value))
                            except Exception as e:
                                _logger.error("Error getting field %s from record: %s", field_name, str(e))
                        else:
                            _logger.warning("Record doesn't have field: %s", field_name)
                    
                    # Apply replacements for record.field_name
                    for old, new in replacements:
                        result = result.replace(old, new)
                    
                    _logger.info("Applied %d replacements for record.field_name placeholders", len(replacements))
                    
                else:
                    _logger.warning("No related record found for thread %s", thread.id)
                    result = content
            else:
                _logger.info("No thread found in context")
                result = content
        else:
            # No related_record or record.field placeholders, just use the content as is
            result = content
        
        final_result = super()._substitute_placeholders(result, arguments)
        return final_result