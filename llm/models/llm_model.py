from odoo import api, fields, models


class LLMModel(models.Model):
    _name = "llm.model"
    _description = "LLM Model"
    _inherit = ["mail.thread"]

    name = fields.Char(required=True)
    provider_id = fields.Many2one("llm.provider", required=True, ondelete="cascade")
    publisher_id = fields.Many2one(
        "llm.publisher",
        string="Publisher",
        ondelete="restrict",
        tracking=True,
        help="The organization or entity that published this model",
    )

    model_use = fields.Selection(
        selection="_get_available_model_usages",
        required=True,
        default="chat",
    )
    default = fields.Boolean(default=False)
    active = fields.Boolean(default=True)

    # Model details
    details = fields.Json()
    model_info = fields.Json()
    parameters = fields.Text()
    template = fields.Text()

    generation_config_id = fields.Many2one(
        "llm.generation.config",
        string="Generation Configuration",
        tracking=True,
        help="Defines input/output schemas for non-chat generation tasks using this model."
    )

    @api.model
    def _get_available_model_usages(self):
        return [
            ("embedding", "Embedding"),
            ("completion", "Completion"),
            ("chat", "Chat"),
            ("multimodal", "Multimodal"),
            ("image_generation", "Image Generation"),
            ("audio_generation", "Audio Generation"),
            ("video_generation", "Video Generation"),
        ]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.default:
                # Ensure only one default per provider/use combo
                self.search(
                    [
                        ("provider_id", "=", record.provider_id.id),
                        ("model_use", "=", record.model_use),
                        ("default", "=", True),
                        ("id", "!=", record.id),
                    ]
                ).write({"default": False})
        return records

    def chat(self, messages, stream=False, **kwargs):
        """Send chat messages using this model"""
        return self.provider_id.chat(messages, model=self, stream=stream, **kwargs)

    def embedding(self, texts):
        """Generate embeddings using this model"""
        return self.provider_id.embedding(texts, model=self)

    def action_open_fetch_this_model_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": f"Fetch Update for {self.name}",
            "res_model": "llm.fetch.models.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_provider_id": self.provider_id.id,
                "default_model_to_fetch": self.name,
            },
        }
    
    def _is_generative_task_model(self):
        """ Helper to check if model_use indicates a non-chat/embedding generative task. """
        self.ensure_one()
        return self.model_use in ['image_generation', 'audio_generation', 'video_generation']
        
    def action_generate_llm_generation_config(self):
        """Generate a generation configuration from the model's details.
        This reads from self.details and dispatches to the provider.
        """
        self.ensure_one()
            
        # Dispatch to provider-specific implementation
        self.provider_id._dispatch(
            "get_config_from_raw_schema",
            model_record=self
        )

        return True
    
    def action_generate_media(self):
        self.ensure_one()
        
        # Check if we have a generation config
        if not self.generation_config_id and self._is_generative_task_model():
            return self.action_generate_llm_generation_config()
        
        # Prepare inputs based on the model type
        if self._is_generative_task_model():
            # For media generation models, we need to structure the input according to Replicate's API
            inputs = {
                "input": {
                    "prompt": "A beautiful sunset over mountains"
                }
            }
        else:
            raise ValueError(f"Model {self.name} is not configured for media generation")
        
        # Dispatch to provider-specific implementation
        result = self.provider_id._dispatch(
            "generate_media",
            inputs=inputs,
            model_record=self
        )
        
        # Log the result
        return result
    
    def generate_media(self, inputs):
        """Generate content using this model with the specified inputs.
        
        Args:
            inputs (dict): The input parameters for generation according to the schema
            
        Returns:
            The generated content (format depends on the model type and configuration)
        """
        self.ensure_one()
        
        # Validate model is configured for generation
        if not self._is_generative_task_model():
            raise ValueError(f"Model {self.name} is not configured for generation tasks")
            
        if not self.generation_config_id:
            raise ValueError(f"Model {self.name} requires a generation configuration")
        
        # Dispatch to provider-specific implementation
        return self.provider_id._dispatch(
            "generate_media",
            inputs=inputs,
            model_record=self
        )
