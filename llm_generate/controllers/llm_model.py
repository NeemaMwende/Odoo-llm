import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class LLMModelController(http.Controller):
    @http.route("/llm/model/gen_config", type="json", auth="user")
    def get_llm_model_gen_config(self, model_id):
        """Get the generation config for a model

        Args:
            model_id: ID of the LLM model

        Returns:
            dict: The generation config data
        """
        try:
            model = request.env["llm.model"].get_model_gen_config_by_id(model_id)

            input_schema_str = model["input_schema"]
            output_schema_str = model["output_schema"]
            parsed_input_schema = None
            parsed_output_schema = None

            if input_schema_str:
                parsed_input_schema = json.loads(input_schema_str)
            else:
                raise ValueError("Input schema is not valid JSON")

            if output_schema_str:
                parsed_output_schema = json.loads(output_schema_str)
            else:
                raise ValueError("Output schema is not valid JSON")

            return {
                "input_schema": parsed_input_schema,
                "output_schema": parsed_output_schema,
                "model_id": model["model_id"],
                "model_name": model["model_name"],
            }
        except Exception as e:
            _logger.error(
                f"Error in get_llm_model_gen_config for model {model_id}: {e}",
                exc_info=True,
            )
            return {"error": str(e)}
