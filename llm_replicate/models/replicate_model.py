import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class LLMModel(models.Model):
    _inherit = "llm.model"

    replicate_version = fields.Char(
        string="Version",
        help="Specific version of the Replicate model to use. Format: alphanumeric hash ID. Leave empty to use the latest version. Some unofficial models requires setting it.",
        tracking=True,
    )

    is_replicate_provider = fields.Boolean(
        string="Is Replicate Provider",
        compute="_compute_is_replicate_provider",
        store=False,
    )

    @api.depends("provider_id", "provider_id.service")
    def _compute_is_replicate_provider(self):
        for record in self:
            record.is_replicate_provider = (
                record.provider_id.service == "replicate"
                if record.provider_id
                else False
            )

    def write(self, vals):
        """Override write to auto-generate schema when details or model_use changes"""
        result = super().write(vals)

        # Process if details or model_use was changed
        if 'details' in vals or 'model_use' in vals:
            for record in self.filtered('is_replicate_provider'):
                # Only for generation models with OpenAPI schema
                # The check for "not input_schema" prevents infinite recursion
                if (
                    record.model_use in ["generation", "image_generation"]
                    and record.details
                    and record.details.get("latest_version", {}).get("openapi_schema")
                    and not record.details.get("input_schema")
                ):
                    record.provider_id.replicate_generate_io_schema(record)

        return result

    def _replicate_model_name_with_version(self):
        """Get the full model name including version if specified"""
        self.ensure_one()
        if self.replicate_version and self.replicate_version.strip():
            return f"{self.name}:{self.replicate_version.strip()}"
        return None
