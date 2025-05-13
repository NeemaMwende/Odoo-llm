from odoo import api, fields, models


class LLMModel(models.Model):
    _inherit = "llm.model"

    input_schema = fields.Text(
        string="Input Schema",
        help="JSON Schema defining the input parameters for this generation task",
        tracking=True,
    )
    output_schema = fields.Text(
        string="Output Schema",
        help="JSON Schema defining the output parameters for this generation task",
        tracking=True,
    )

    @api.model
    def _get_available_model_usages(self):
        available_usages = super()._get_available_model_usages()
        return available_usages + [
            ("image_generation", "Image Generation"),
        ]

    def _is_generative_task_model(self):
        """Helper to check if model_use indicates a non-chat/embedding generative task."""
        self.ensure_one()
        return self.model_use in ["image_generation"]

    def action_generate_io_schema(self):
        """Generate a generation configuration from the model's details.
        This reads from self.details and dispatches to the provider.
        """
        self.ensure_one()

        # Dispatch to provider-specific implementation
        self.provider_id._dispatch("generate_io_schema", model_record=self)

        return True

    def generate_media(self, inputs, stream=False):
        """Generate content using this model with the specified inputs.

        Args:
            inputs (dict): The input parameters for generation according to the schema

        Returns:
            The generated content (format depends on the model type and configuration)
        """
        self.ensure_one()

        # Validate model is configured for generation
        if not self._is_generative_task_model():
            raise ValueError(
                f"Model {self.name} is not configured for generation tasks"
            )

        # Dispatch to provider-specific implementation
        return self.provider_id._dispatch(
            "generate_media", inputs=inputs, model_record=self, stream=stream
        )

    def format_generation_response(self, raw_response):
        """Format the raw generation response according to the output processing config

        Args:
            raw_response: The raw response from the provider

        Returns:
            Processed response in the format specified by the config
        """
        self.ensure_one()

        # Dispatch to provider-specific implementation
        return self.provider_id._dispatch(
            "format_generation_response",
            raw_response=raw_response,
            output_schema=self.output_schema,
        )

    @api.model
    def get_model_gen_io_by_id(self, model_id):
        model = self.browse(int(model_id))
        if not model.exists():
            raise ValueError(f"Model {model_id} not found")

        return {
            "input_schema": model.input_schema,
            "output_schema": model.output_schema,
            "model_id": model.id,
            "model_name": model.name,
        }
