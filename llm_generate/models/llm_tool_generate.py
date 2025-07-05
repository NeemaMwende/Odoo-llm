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

    def odoo_generate_execute(
        self, model_id: int, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        """Generate content using the specified model and inputs."""
        self.ensure_one()

        try:
            model = self.env["llm.model"].browse(int(model_id))
            if not model.exists():
                return {"error": f"Model {model_id} not found"}

            # Use model's generate method - now returns tuple (output_data, urls)
            output_data, urls = model.generate(inputs)

            # Process URLs for tool response
            processed_urls = []
            markdown_parts = []

            for i, url_data in enumerate(urls):
                processed_urls.append(url_data)
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

            return {
                "success": True,
                "output_data": output_data,
                "urls": processed_urls,
                "markdown": "\n\n".join(markdown_parts),
                "content_count": len(urls)
            }

        except Exception as e:
            _logger.error(f"Error in content generation: {e}")
            return {"error": f"Generation failed: {str(e)}", "success": False}
