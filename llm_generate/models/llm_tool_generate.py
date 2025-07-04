import logging
from typing import Any

from odoo import api, models

_logger = logging.getLogger(__name__)


class LLMToolGenerate(models.Model):
    _inherit = "llm.tool"

    @api.model
    def _get_available_implementations(self):
        implementations = super()._get_available_implementations()
        return implementations + [("odoo_generate", "Odoo Content Generator")]

    def odoo_generate_execute(self, model_id: int, inputs: dict[str, Any]) -> dict[str, Any]:
        """Generate content using the specified model and inputs."""
        self.ensure_one()

        try:
            model = self.env["llm.model"].browse(int(model_id))
            if not model.exists():
                return {"error": f"Model {model_id} not found"}

            # Use model's generate method
            result = model.generate(inputs)
            
            # Handle streaming response
            if hasattr(result, '__iter__') and not isinstance(result, (str, dict)):
                # Get first chunk for non-streaming tools
                for chunk in result:
                    if chunk.get("content"):
                        result = chunk["content"]
                        break
            
            # Format result
            if isinstance(result, list):
                # Handle multiple results (e.g., image URLs)
                markdown = []
                for i, item in enumerate(result):
                    if isinstance(item, str) and item.startswith(('http://', 'https://')):
                        markdown.append(f"![Generated Content {i+1}]({item})")
                    else:
                        markdown.append(str(item))
                
                return {
                    "success": True,
                    "content": result,
                    "markdown": "\n".join(markdown)
                }
            
            return {
                "success": True,
                "content": result,
                "markdown": str(result)
            }

        except Exception as e:
            _logger.error(f"Error in content generation: {e}")
            return {
                "error": f"Generation failed: {str(e)}",
                "success": False
            }
