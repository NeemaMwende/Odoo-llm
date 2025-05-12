import json
import logging

from odoo import api, http, registry
from odoo.http import Response, request

from odoo.addons.llm_thread.controllers.llm_thread import LLMThreadController

_logger = logging.getLogger(__name__)

class LLMThreadControllerExtended(LLMThreadController):

    def _llm_thread_generate(self, dbname, env, thread_id, user_message_body, generation_inputs=None):
        """Generate LLM responses with streaming and safe yielding."""
        with registry(dbname).cursor() as cr:
            env = api.Environment(cr, env.uid, env.context)
            llmThread = env["llm.thread"].browse(int(thread_id))
            if not llmThread.exists():
                yield from self._safe_yield(
                    f"data: {json.dumps({'type': 'error', 'error': 'LLM Thread not found.'})}\n\n".encode()
                )
                return

            client_connected = True
            try:
                for response in llmThread.generate(user_message_body, generation_inputs=generation_inputs):
                    json_data = json.dumps(response, default=str)
                    success = yield from self._safe_yield(
                        f"data: {json_data}\n\n".encode()
                    )
                    if not success:
                        client_connected = False
                        break

            except GeneratorExit:
                # Client disconnected explicitly
                client_connected = False
                if llmThread.exists() and llmThread._read_is_locked_decorated():
                    llmThread._unlock()
                return

            except Exception as e:
                _logger.exception(f"Error in llm_thread_generate for thread {thread_id}: {e}")
                if llmThread.exists() and llmThread._read_is_locked_decorated():
                    llmThread._unlock()

                if client_connected:
                    success = yield from self._safe_yield(
                        f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n".encode()
                    )
                    if not success:
                        client_connected = False

            finally:
                if client_connected:
                    yield from self._safe_yield(
                        f"data: {json.dumps({'type': 'done'})}\n\n".encode()
                    )
    
    @http.route("/llm/thread/generate-media", type="http", auth="user", csrf=True)
    def llm_thread_generate_media(self, thread_id, message=None, generation_inputs=None, **kwargs):
        headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
        user_message_body = message
        return Response(
            self._llm_thread_generate(
                request.cr.dbname, request.env, thread_id, user_message_body, generation_inputs
            ),
            direct_passthrough=True,
            headers=headers,
        )
            
    @http.route('/llm_thread/get_generation_config', type='json', auth='user')
    def get_generation_config(self, model_id):
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
            _logger.error(f"Error in get_generation_config for model {model_id}: {e}", exc_info=True)
            return {'error': str(e)}
