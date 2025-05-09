import json
import logging

from odoo import _, api, http, registry
from odoo.exceptions import MissingError
from odoo.http import Response, request

_logger = logging.getLogger(__name__)

class LLMThreadController(http.Controller):
    @http.route(
        "/llm/thread/<int:thread_id>/update",
        type="json",
        auth="user",
        methods=["POST"],
        csrf=True,
    )
    def llm_thread_update(self, thread_id, **kwargs):
        try:
            thread = request.env["llm.thread"].browse(thread_id)
            if not thread.exists():
                raise MissingError(_("LLM Thread not found."))
            thread.write(kwargs)
            return {"status": "success"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _safe_yield(self, data_to_yield):
        """Helper generator to yield data safely, handling BrokenPipeError(Disconnected user)."""
        try:
            yield data_to_yield
            return True
        except BrokenPipeError:
            return False
        except Exception:
            return False

    def _llm_thread_generate(self, dbname, env, thread_id, user_message_body):
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
                for response in llmThread.generate(user_message_body):
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

    @http.route("/llm/thread/generate", type="http", auth="user", csrf=True)
    def llm_thread_generate(self, thread_id, message=None, **kwargs):
        headers = {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
        user_message_body = message
        return Response(
            self._llm_thread_generate(
                request.cr.dbname, request.env, thread_id, user_message_body
            ),
            direct_passthrough=True,
            headers=headers,
        )

    @http.route("/llm/message/vote", type="json", auth="user", methods=["POST"])
    def llm_message_vote(self, message_id, vote_value):
        """Updates the user vote on a specific message by calling the model method."""
        try:
            msg_id = int(message_id)
            vote_val = int(vote_value)
            request.env["mail.message"].set_user_vote(msg_id, vote_val)
            return {"success": True}

        except (ValueError, TypeError):
            return {"error": _("Invalid message ID or vote value format.")}
        except Exception as e:
            return {"error": str(e)}
            
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

    @http.route('/llm_thread/generate_media', type='json', auth='user')
    def generate_media(self, thread_id, model_id, inputs):
        """Generate media content using an LLM model
        
        Args:
            thread_id: ID of the thread to post the generated media to
            model_id: ID of the LLM model to use for generation
            inputs: Input parameters for the model
            
        Returns:
            dict: Information about the generated media and created message
        """
        try:
            thread = request.env['llm.thread'].browse(int(thread_id))
            if not thread.exists():
                return {'error': 'Thread not found'}
                
            model = request.env['llm.model'].browse(int(model_id))
            if not model.exists():
                return {'error': 'Model not found'}
            
            # Generate the media
            result = model.action_generate_media(inputs)
            
            # Create attachments for the generated media
            attachments = []
            if isinstance(result, list):
                for i, url in enumerate(result):
                    attachment = request.env['ir.attachment'].create({
                        'name': f'Generated Media {i+1}',
                        'type': 'url',
                        'url': url,
                        'res_model': thread._name,
                        'res_id': thread.id,
                    })
                    attachments.append(attachment.id)
            elif isinstance(result, str):
                attachment = request.env['ir.attachment'].create({
                    'name': 'Generated Media',
                    'type': 'url',
                    'url': result,
                    'res_model': thread._name,
                    'res_id': thread.id,
                })
                attachments.append(attachment.id)
            
            # Post a message with the attachments
            message = thread.message_post(
                body="Generated media content",
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                attachment_ids=attachments,
            )
            
            return {
                'message_id': message.id,
                'attachments': attachments,
                'result': result
            }
        except Exception as e:
            return {'error': str(e)}
