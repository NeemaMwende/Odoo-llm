import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class LLMModelController(http.Controller):
    @http.route('/llm/model/gen_config', type='json', auth='user')
    def get_llm_model_gen_config(self, model_id):
        """Get the generation config for a model
        
        Args:
            model_id: ID of the LLM model
            
        Returns:
            dict: The generation config data
        """
        try:
            model = request.env['llm.model'].browse(int(model_id))
            
            if not model.exists():
                return {'error': 'Model not found'}
            
            if not model.generation_config_id:
                return {'error': 'No generation config found for this model'}

            input_schema_str = model.generation_config_id.input_schema
            output_schema_str = model.generation_config_id.output_schema_raw
            parsed_input_schema = None
            parsed_output_schema = None

            try:
                if input_schema_str:
                    parsed_input_schema = json.loads(input_schema_str)
            except json.JSONDecodeError as e:
                _logger.error(f"Failed to parse input_schema for model {model_id}: {e}")
                return {'error': f"Invalid input schema format: {e}"}

            try:
                if output_schema_str:
                    parsed_output_schema = json.loads(output_schema_str)
            except json.JSONDecodeError as e:
                _logger.error(f"Failed to parse output_schema for model {model_id}: {e}")
                return {'error': f"Invalid output schema format: {e}"}
            
            return {
                'input_schema': parsed_input_schema,
                'output_schema': parsed_output_schema,
                'model_id': model.id,
                'model_name': model.name
            }
        except Exception as e:
            _logger.error(f"Error in get_llm_model_gen_config for model {model_id}: {e}", exc_info=True)
            return {'error': str(e)}
